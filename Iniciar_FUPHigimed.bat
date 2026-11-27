@echo off
cd /d "%~dp0"
echo ====================================================
echo   FUPHigimed - Frota Propria & Tecnica (Banco Local)
echo ====================================================
py criar_banco.py
echo Abrindo sistema local em http://localhost:8501 ...
py -m streamlit run app.py --server.port 8501
pause