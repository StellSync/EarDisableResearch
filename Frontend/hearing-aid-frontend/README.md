# Project Setup Guide

This project uses **Next.js** for the frontend and **FastAPI** for the backend.

---

## 1. Start the Backend

Run the FastAPI server:

```
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

API will be available at:
```
http://127.0.0.1:8000
```

---

## 2. Start the Frontend

Inside the frontend directory:

```
npm install
npm run dev
```

Then open the app in your browser:
```
http://localhost:3000
```

The UI will live-update when edits are made.

---

## Pages / Routes

| Page | URL | Description |
|------|-----|-------------|
| Quiz / Activities | http://localhost:3000/form | User interactivity and exercises |
| Doctor Dashboard | http://localhost:3000/doc-view | Doctor's patient overview |

---

## Environment Configuration

Make sure the backend URL is set in your `.env` file:

```
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
```

---

## User ID Configuration

The app currently requires a `user_id` (from your login system).  
Update these locations with a valid user ID:

| File | Line Number(s) | Purpose |
|------|----------------|---------|
| `app/form/page.jsx` | line 18 | Main form |
| `app/component/VowelDialog.jsx` | line 142 | Vowel exercise dialog |
| `app/component/ConsonantsDialog.jsx` | line 40, 141 | Consonant exercise dialog |
| `app/component/SentenceDialog.jsx` | line 145 | Sentence forming activity |

---

## Doctor View Setup

To load patient data into the Doctor Dashboard, modify:

```
app/doc-view/page.jsx
```

Fetch and display the patient list from your backend.

---

## Adding More Activities

When adding a new activity:

1. **Add any audio files** used by the activity into the `public/` folder

This ensures audio loads correctly.
