# Hearing Project v0.01 - Full Setup Guide

This project includes a **FastAPI backend** and a **Next.js frontend**. Follow the steps below to set up and run the full system.

---

## Backend Setup (FastAPI)

### 1. Navigate to the project directory:
```
cd hearing_project_v0.01
```

### 2. Install dependencies (only required the first time):
```
pip install -r requirements.txt
```

### 3. Start the backend server:
```
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The backend API will now be running at:
```
http://127.0.0.1:8000
```

---

## Frontend Setup (Next.js)

### 1. Navigate to the frontend directory:
```
cd Frontend/hearing-aid-frontend
```

### 2. Install node dependencies (only required the first time):
```
npm i
```

### 3. Start the frontend development server:
```
npm run dev
```

The frontend will now be available at:
```
http://localhost:3000
```

---

## Summary of Run Commands

| Action | Command |
|-------|---------|
| Start backend | `uvicorn app.main:app --reload --host 127.0.0.1 --port 8000` |
| Start frontend | `npm run dev` |
| Install backend dependencies (first time only) | `pip install -r requirements.txt` |
| Install frontend dependencies (first time only) | `npm i` |

---

## Notes

- Only install dependencies once unless new packages are added.
- Make sure the backend is running **before** starting and using the frontend.
- Ensure `NEXT_PUBLIC_API_URL` in the frontend `.env` matches your backend server URL (ex: `http://127.0.0.1:8000`).

---

You are now ready to use the application! 🎧🧠
