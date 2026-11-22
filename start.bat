@echo off
setlocal
if not exist .venv (
  python -m venv .venv
  call .venv\Scripts\activate.bat
  python -m pip install --upgrade pip
  python -m pip install -r requirements.txt
) else (
  call .venv\Scripts\activate.bat
)
if not exist frontend\dist (
  pushd frontend
  call npm install
  call npm run build
  popd
)
python run.py
endlocal
