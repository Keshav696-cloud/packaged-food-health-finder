# Packaged Food Health Analyzer

A local Flask mini-project prototype based on the supplied synopsis. It supports label-image upload, OCR text extraction, editable nutrition fields, ingredient parsing, an explainable demo scoring heuristic, SQLite analysis history, and sample products.

## Important limitations

- OCR needs the Tesseract executable installed separately; `pytesseract` is only the Python wrapper.
- OCR extraction is best-effort. Always review values, units, and ingredients before analysis.
- The score thresholds and additive notes in this starter project are demonstration rules, not a validated medical tool or official Nutri-Score implementation. Replace/verify them against current FSSAI/WHO and other appropriate authoritative references before academic submission.
- The app does not claim that an ingredient is medically safe. An unknown additive is marked for reference checking.
- Barcode scanning and online product lookup are not implemented in this first version.

## 1. Install Python dependencies

Open PowerShell in this folder and run:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 2. Install Tesseract OCR on Windows

Install the Windows Tesseract OCR application from the UB Mannheim Tesseract distribution (search for `UB Mannheim Tesseract OCR Windows`). During setup, note the installation path. Typical path:

`C:\Program Files\Tesseract-OCR\tesseract.exe`

If Python cannot find Tesseract, set the path in `app.py` immediately after imports and before `run_ocr` is called:

```python
import pytesseract
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
```

If your installation uses another location, use that path instead.

## 3. Run the app

```powershell
python app.py
```

Open `http://127.0.0.1:5000` in your browser. The SQLite database is created automatically as `food_analyzer.db`.

## Features

- Responsive landing page
- Upload a label image and preview it
- OCR with image preprocessing
- Editable nutrition values and ingredients
- Demo sample products
- Rule-based score with warning explanations
- Ingredient/additive reference checks
- Saved analysis history in SQLite
- No external API required for core functionality

## Suggested test sequence

1. Start the app and open the home page.
2. Click one of the sample products and run the analysis.
3. Return home and upload a clear label image.
4. Check the OCR text and correct all values/units.
5. Analyze and confirm that the result appears in Saved analyses.

## Troubleshooting

- `TesseractNotFoundError`: install Tesseract and set `pytesseract.pytesseract.tesseract_cmd` to its executable path.
- `No module named flask` or `pytesseract`: activate `.venv` and run `pip install -r requirements.txt`.
- OCR returns empty or incorrect values: use a sharp, straight-on image with high contrast; crop tightly around the label; verify all extracted data manually.
- Port 5000 is busy: change the final line to `app.run(debug=True, port=5001)` and open `http://127.0.0.1:5001`.
