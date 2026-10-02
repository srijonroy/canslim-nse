@echo off
rem CAN SLIM tracker app (local). Opens in the browser at http://localhost:8501
cd /d C:\Project\asd
python -m streamlit run tracker_app.py --server.headless false --browser.gatherUsageStats false --server.address localhost
