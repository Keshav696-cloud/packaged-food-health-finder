from flask import Flask, render_template, request, redirect, url_for, flash
from werkzeug.utils import secure_filename
from pathlib import Path
import sqlite3, re, os
import pytesseract

pytesseract.pytesseract.tesseract_cmd = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)

try:
    from PIL import Image, ImageOps, ImageEnhance, ImageFilter
    import pytesseract
except ImportError:
    Image = None
    pytesseract = None

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / 'uploads'
DB_PATH = BASE_DIR / 'food_analyzer.db'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'bmp'}
UPLOAD_DIR.mkdir(exist_ok=True)
app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'local-dev-key-change-before-deployment')
app.config['MAX_CONTENT_LENGTH'] = 8 * 1024 * 1024

NUTRIENTS = [
    ('energy', 'Energy', 'kcal'), ('total_fat', 'Total fat', 'g'),
    ('saturated_fat', 'Saturated fat', 'g'), ('trans_fat', 'Trans fat', 'g'),
    ('carbohydrates', 'Carbohydrates', 'g'), ('total_sugars', 'Total sugars', 'g'),
    ('added_sugars', 'Added sugars', 'g'), ('protein', 'Protein', 'g'),
    ('sodium', 'Sodium', 'mg'), ('fibre', 'Fibre', 'g')
]

SAMPLE_PRODUCTS = {
    'instant_noodles': {
        'name': 'Instant noodles (sample)', 'category': 'Instant noodles',
        'energy': 450, 'total_fat': 18, 'saturated_fat': 8, 'trans_fat': 0.1,
        'carbohydrates': 62, 'total_sugars': 3, 'added_sugars': 2,
        'protein': 8, 'sodium': 900, 'fibre': 3,
        'ingredients': 'Wheat flour (maida), edible vegetable oil, iodized salt, wheat gluten, thickener (INS 508), acidity regulator (INS 451), flavour enhancer (INS 621), spices and condiments, dehydrated vegetables.'
    },
    'biscuits': {
        'name': 'Sweet biscuits (sample)', 'category': 'Biscuits',
        'energy': 480, 'total_fat': 21, 'saturated_fat': 10, 'trans_fat': 0,
        'carbohydrates': 68, 'total_sugars': 24, 'added_sugars': 20,
        'protein': 6, 'sodium': 350, 'fibre': 2,
        'ingredients': 'Refined wheat flour, sugar, edible vegetable oil, raising agents, salt, flavouring.'
    },
    'cornflakes': {
        'name': 'Corn flakes (sample)', 'category': 'Breakfast cereal',
        'energy': 370, 'total_fat': 1, 'saturated_fat': 0.3, 'trans_fat': 0,
        'carbohydrates': 84, 'total_sugars': 8, 'added_sugars': 6,
        'protein': 7, 'sodium': 700, 'fibre': 3,

        'ingredients': 'Maize, sugar, malt extract, salt, vitamins and minerals.'
    }
}

ADDITIVE_RULES = {
    'INS 621': ('Review / limit', 'Flavour enhancer (monosodium glutamate); sensitivity varies by person.'),
    'INS 211': ('Review / limit', 'Preservative; check product context and applicable guidance.'),
    'INS 320': ('Review / limit', 'Antioxidant additive; consult a reliable, current reference before classifying.'),
    'INS 102': ('Review / limit', 'Synthetic colour; check applicable regulations and individual sensitivities.'),
    'INS 951': ('Review / limit', 'Sweetener; check label and individual dietary needs.'),
    'INS 508': ('Generally permitted', 'Potassium chloride is used as a food additive; this is not a personal safety assessment.'),
    'INS 451': ('Generally permitted', 'Triphosphates are used for technological purposes; amount and context matter.'),
    'INS 330': ('Generally permitted', 'Citric acid is commonly used as an acidity regulator.'),
    'INS 500': ('Generally permitted', 'Sodium carbonates are commonly used as raising/acidity agents.')
}


def db_connect():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    with db_connect() as con:
        con.execute('''CREATE TABLE IF NOT EXISTS analyses (
            id INTEGER PRIMARY KEY AUTOINCREMENT, product_name TEXT NOT NULL,
            category TEXT, nutrients_json TEXT NOT NULL, ingredients TEXT NOT NULL,
            score INTEGER NOT NULL, status TEXT NOT NULL, warnings_json TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        con.execute('''CREATE TABLE IF NOT EXISTS additive_reference (
            code TEXT PRIMARY KEY, status TEXT NOT NULL, explanation TEXT NOT NULL)''')
        for code, (status, explanation) in ADDITIVE_RULES.items():
            con.execute('INSERT OR REPLACE INTO additive_reference(code,status,explanation) VALUES(?,?,?)',
                        (code, status, explanation))

init_db()


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def run_ocr(image_path):
    if Image is None or pytesseract is None:
        raise RuntimeError('OCR packages are not installed. Run: pip install -r requirements.txt')
    try:
        img = Image.open(image_path).convert('RGB')
        img = ImageOps.grayscale(img)
        img = ImageOps.autocontrast(img)
        img = img.resize((img.width * 2, img.height * 2))
        img = ImageEnhance.Contrast(img).enhance(1.5)
        return pytesseract.image_to_string(img, config='--psm 6')
    except Exception as exc:
        raise RuntimeError('Could not read this image. Check that Tesseract OCR is installed and the image is clear. Details: ' + str(exc))


def parse_number(text, patterns, default=0.0):
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            raw = match.group(1).replace(',', '.')
            try:
                return float(raw)
            except ValueError:
                pass
    return default


def extract_nutrients(ocr_text):
    # Parse one line at a time so a generic 'fat' match does not accidentally
    # capture the saturated-fat value. These are suggestions for user review.
    labels = {
        'energy': r'energy|calories|kcal',
        'total_fat': r'^(?!.*saturated)(?!.*trans).*\b(?:total\s+fat|fat)\b',
        'saturated_fat': r'saturated\s+fat|sat(?:urated)?\.?\s*fat',
        'trans_fat': r'trans\s+fat',
        'carbohydrates': r'carbohydrates?',
        'total_sugars': r'^(?!.*added).*\b(?:total\s+)?sugars?\b',
        'added_sugars': r'added\s+sugars?',
        'protein': r'protein',
        'sodium': r'sodium',
        'fibre': r'(?:dietary\s+)?(?:fibre|fiber)'
    }
    values = {key: 0.0 for key in labels}
    for line in ocr_text.lower().replace('：', ':').splitlines():
        for key, label_pattern in labels.items():
            if re.search(label_pattern, line, re.I):
                match = re.search(r'(-?\d+(?:[.,]\d+)?)', line)
                if match:
                    try:
                        values[key] = max(0.0, float(match.group(1).replace(',', '.')))
                    except ValueError:
                        pass
                break
    return values


def extract_ingredients(ocr_text):
    # Keep the text following an Ingredients heading, often printed as a paragraph.
    match = re.search(r'(?:ingredients|ingredient\s+list)\s*[:\-]?\s*(.*)', ocr_text, re.I | re.S)
    if not match:
        return ''
    text = match.group(1).strip()
    # Stop at common unrelated label headings if OCR captured the rest of the package.
    text = re.split(r'\n\s*(?:allergen information|contains|manufactured by|storage instructions|customer care|net quantity|best before)\b', text, maxsplit=1, flags=re.I)[0]
    return re.sub(r'\s+', ' ', text).strip(' :;-')[:3000]


def classify_ingredients(ingredients):
    results = []
    if not ingredients.strip():
        return results
    tokens = [x.strip(' .;') for x in re.split(r',|\n|;(?=\s*[A-Za-z])', ingredients) if x.strip(' .;')]
    for token in tokens:
        upper = token.upper()
        codes = re.findall(r'INS\s*[-:]?\s*\d{3,4}[A-Z]?', upper)
        matched = False
        for code in codes:
            code = re.sub(r'\s+', ' ', code).replace('INS ', 'INS ')
            status, explanation = ADDITIVE_RULES.get(code, ('Check reference', 'No local rule is available for this additive; verify against an authoritative current source.'))
            results.append({'ingredient': token, 'code': code, 'status': status, 'explanation': explanation})
            matched = True
        if not matched:
            low = token.lower()
            if any(x in low for x in ['maida', 'refined wheat flour', 'refined flour']):
                status, explanation = 'Use with awareness', 'Refined flour is generally lower in fibre than whole-grain alternatives.'
            elif any(x in low for x in ['palm oil', 'hydrogenated oil', 'shortening']):
                status, explanation = 'Review quantity', 'Check the saturated-fat and trans-fat values on the nutrition panel.'
            elif any(x in low for x in ['salt', 'iodized salt']):
                status, explanation = 'Review quantity', 'Compare the sodium value with an appropriate serving-size guideline.'
            else:
                status, explanation = 'No local flag', 'No specific local rule matched this ingredient; this does not certify it as healthy or safe.'
            results.append({'ingredient': token, 'code': '—', 'status': status, 'explanation': explanation})
    return results


def analyze_food(nutrients, ingredients):
    # Transparent educational heuristic, not a clinically validated or official Nutri-Score formula.
    score = 100
    warnings = []
    checks = [
        ('energy', 400, 10, 'Energy is high per 100 g.'),
        ('total_fat', 17.5, 10, 'Total fat is high per 100 g.'),
        ('saturated_fat', 5, 12, 'Saturated fat is high per 100 g.'),
        ('trans_fat', 0.5, 18, 'Trans fat is above the demo threshold.'),
        ('total_sugars', 22.5, 12, 'Total sugars are high per 100 g.'),
        ('added_sugars', 10, 10, 'Added sugars are high per 100 g.'),
        ('sodium', 600, 14, 'Sodium is high per 100 g.'),
    ]
    for key, threshold, penalty, message in checks:
        value = float(nutrients.get(key, 0) or 0)
        if value > threshold:
            score -= penalty
            warnings.append(message)
    if float(nutrients.get('fibre', 0) or 0) < 3:
        score -= 5
        warnings.append('Fibre is low in this sample rule set.')
    if re.search(r'INS\s*621', ingredients, re.I):
        warnings.append('Contains INS 621; review the ingredient context and your own dietary needs.')
    score = max(0, min(100, score))
    status = 'Good balance' if score >= 75 else ('Moderate' if score >= 55 else 'Needs caution')
    if not warnings:
        warnings.append('No high values were flagged by the current demo thresholds; this is not a guarantee of overall healthfulness.')
    return score, status, warnings


def to_float(value):
    try:
        return max(0.0, float(str(value).strip().replace(',', '.')))
    except (ValueError, TypeError):
        return 0.0


@app.route('/', methods=['GET'])
def index():
    return render_template('index.html', products=SAMPLE_PRODUCTS)


@app.route('/scan', methods=['POST'])
def scan():
    if 'label_image' not in request.files or not request.files['label_image'].filename:
        flash('Choose an image of the nutrition label first.', 'error')
        return redirect(url_for('index'))
    file = request.files['label_image']
    if not allowed_file(file.filename):
        flash('Please upload a PNG, JPG, JPEG, WEBP or BMP image.', 'error')
        return redirect(url_for('index'))
    safe_name = secure_filename(file.filename)
    saved_path = UPLOAD_DIR / safe_name
    # Avoid overwriting files with the same name.
    if saved_path.exists():
        saved_path = UPLOAD_DIR / f'{saved_path.stem}_{os.urandom(3).hex()}{saved_path.suffix}'
    file.save(saved_path)
    try:
        raw_text = run_ocr(saved_path)
        nutrients = extract_nutrients(raw_text)
        extracted_ingredients = extract_ingredients(raw_text)
        if not raw_text.strip():
            flash('OCR did not detect readable text. Try a sharper, well-lit image.', 'error')
    except RuntimeError as exc:
        raw_text = ''
        extracted_ingredients = ''
        nutrients = {key: 0.0 for key, _, _ in NUTRIENTS}
        flash(str(exc), 'error')
    return render_template('review.html', nutrients=nutrients, nutrient_defs=NUTRIENTS,
                           raw_text=raw_text, image_name=saved_path.name, ingredients=extracted_ingredients)


@app.route('/sample/<sample_key>')
def sample(sample_key):
    product = SAMPLE_PRODUCTS.get(sample_key)
    if not product:
        flash('Sample product not found.', 'error')
        return redirect(url_for('index'))
    return render_template('review.html', nutrients={k: product.get(k, 0) for k, _, _ in NUTRIENTS},
                           nutrient_defs=NUTRIENTS, raw_text='Loaded from built-in demonstration data. Values are illustrative.',
                           image_name='', product_name=product['name'], category=product['category'],
                           ingredients=product['ingredients'])


@app.route('/analyze', methods=['POST'])
def analyze():
    nutrients = {key: to_float(request.form.get(key, 0)) for key, _, _ in NUTRIENTS}
    ingredients = request.form.get('ingredients', '').strip()
    product_name = request.form.get('product_name', '').strip() or 'Scanned food product'
    category = request.form.get('category', '').strip() or 'Packaged food'
    score, status, warnings = analyze_food(nutrients, ingredients)
    ingredient_rows = classify_ingredients(ingredients)
    import json
    with db_connect() as con:
        cur = con.execute('INSERT INTO analyses(product_name, category, nutrients_json, ingredients, score, status, warnings_json) VALUES(?,?,?,?,?,?,?)',
                           (product_name, category, json.dumps(nutrients), ingredients, score, status, json.dumps(warnings)))
        analysis_id = cur.lastrowid
    return render_template('results.html', product_name=product_name, category=category,
                           nutrients=nutrients, nutrient_defs=NUTRIENTS, ingredients=ingredients,
                           ingredient_rows=ingredient_rows, score=score, status=status,
                           warnings=warnings, analysis_id=analysis_id)


@app.route('/saved')
def saved():
    import json
    with db_connect() as con:
        rows = con.execute('SELECT * FROM analyses ORDER BY created_at DESC LIMIT 30').fetchall()
    records = []
    for row in rows:
        records.append({**dict(row), 'warnings': json.loads(row['warnings_json'])})
    return render_template('saved.html', records=records)


@app.errorhandler(413)
def too_large(_error):
    flash('Image is too large. Please upload an image under 8 MB.', 'error')
    return redirect(url_for('index'))


if __name__ == '__main__':
    app.run(debug=True)
