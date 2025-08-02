 
# PayMetrics 💰

A modern personal finance management dashboard built with React and Flask.

## 🚀 Features

- **Dashboard Analytics** - Real-time spending insights with interactive charts
- **Google OAuth** - Secure authentication with Google Sign-In
- **Multi-Account Support** - Manage multiple bank accounts (Credit/Debit/Savings)
- **Transaction Filtering** - Search and filter by account, category, date
- **Professional UI** - Clean, responsive Material-UI design
- **Data Visualization** - Interactive pie charts and spending breakdowns

## 🛠️ Tech Stack

**Frontend:**
- React 18 with TypeScript
- Material-UI (MUI)
- Recharts for visualization
- Framer Motion animations

**Backend:**
- Python Flask REST API
- SQLAlchemy ORM
- JWT Authentication
- Google OAuth integration

## 📁 Project Structure

paymetrics/
├── frontend/ # React TypeScript app
│ ├── src/
│ │ ├── components/
│ │ ├── pages/
│ │ └── App.tsx
│ └── package.json
├── backend/ # Flask API
│ ├── app.py
│ ├── models.py
│ └── requirements.txt
└── README.md


## 🏃‍♂️ Getting Started

### Prerequisites
- Node.js 16+ and npm
- Python 3.8+

### Installation

1. **Clone the repository**

git clone https://github.com/vihashni08/PayMetrics.git
cd PayMetrics

text

2. **Backend Setup**
cd backend
python -m venv venv
venv\Scripts\activate # Windows
pip install -r requirements.txt
python app.py

text

3. **Frontend Setup**
cd frontend
npm install
npm start

text

4. **Access the Application**
- Frontend: http://localhost:3000
- Backend API: http://localhost:5000

## 🔑 Environment Variables

Create `.env` files in backend directory:

SECRET_KEY=your-secret-key
JWT_SECRET_KEY=your-jwt-secret
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret

text

## 🎯 Demo

Try the **Demo Mode** by clicking "Continue with Demo" to explore features with sample data.

## 👨‍💻 Author

**Vihashni** - [GitHub](https://github.com/vihashni08)

---

⭐ Star this repository if you find it helpful!