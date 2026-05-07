# Contributing to ModelSentinel

## Setup
```bash
git clone https://github.com/trinadhsriram02/modelsentinel.git
cd modelsentinel
python -m venv venv
source venv/bin/activate  # Mac/Linux
venv\Scripts\activate.bat  # Windows
pip install -r requirements.txt
cp .env.example .env
# Fill in your GROQ_API_KEY in .env
```

## Running tests
```bash
pytest tests/ -v
```

## Running locally
```bash
python -m src.api.main     # Terminal 1
streamlit run dashboard.py  # Terminal 2
```

## Project structure
See README.md for full directory explanation.