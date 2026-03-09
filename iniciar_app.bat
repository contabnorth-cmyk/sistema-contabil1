@echo off
cd /d %~dp0
python -m pip install -r requirements.txt
start http://localhost:8501
python -m streamlit run app.py
