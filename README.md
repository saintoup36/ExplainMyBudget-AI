# 💰 ExplainMyBudget AI

ExplainMyBudget AI is an intelligent, user-friendly financial assistant that helps users understand, analyze, and improve their budgeting decisions using AI-powered insights.

---

## 🚀 Features

* 📊 **Smart Budget Analysis**
  Upload or input your financial data and receive clear insights.

* 🧠 **AI-Powered Recommendations**
  Get personalized suggestions to improve spending and savings.

* 🔍 **Expense Tracking & Breakdown**
  Understand where your money goes with intuitive summaries.

* 💬 **Ask Your Budget (AI Q&A)**
  Interact with your financial data using natural language.

* 🌍 **Multi-language Support**
  Interface and insights available in multiple languages.

* 🔐 **Secure Account Access**
  User authentication with session-based access.

* 💎 **Premium Features (Stripe Integration)**
  Unlock advanced tools via subscription.

---

## 💳 Pricing

* **Free Plan**

  * Basic features
  * Limited access

* **Premium Plan ($12.99/month)**

  * Full AI insights
  * Advanced analysis tools
  * Unlimited usage

---

## 🛠️ Tech Stack

* **Frontend/UI:** Streamlit
* **Backend Logic:** Python
* **AI Engine:** OpenAI API
* **Payments:** Stripe
* **Data Handling:** Pandas
* **Reporting:** ReportLab

---

## ⚙️ Installation (Local Setup)

1. Clone the repository:

```bash
git clone https://github.com/saintoup36/ExplainMyBudget-AI.git
cd ExplainMyBudget-AI
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Create a `.env` file:

```env
OPENAI_API_KEY=your_openai_key
STRIPE_PAYMENT_LINK_SUBSCRIPTION=your_stripe_link
STRIPE_PAYMENT_LINK_ONE_TIME=your_stripe_link
APP_BASE_URL=http://localhost:8501
```

4. Run the app:

```bash
streamlit run app.py
```

---

## 🔐 Environment Variables

| Variable                         | Description               |
| -------------------------------- | ------------------------- |
| OPENAI_API_KEY                   | OpenAI API key            |
| STRIPE_PAYMENT_LINK_SUBSCRIPTION | Monthly subscription link |
| STRIPE_PAYMENT_LINK_ONE_TIME     | One-time payment link     |
| APP_BASE_URL                     | App base URL              |

---

## 🌐 Deployment

This app is designed for deployment on Streamlit Cloud.

1. Push code to GitHub
2. Connect repo on Streamlit
3. Add secrets in **App Settings → Secrets**

---

## ⚠️ Security Notes

* Never commit `.env` files
* Keep API keys private
* Use Streamlit Secrets in production

---

## 📌 Roadmap

* ✅ Stripe payment integration
* 🔜 Supabase user persistence
* 🔜 Webhook-based payment verification
* 🔜 Advanced financial forecasting

---

## 🤝 Contributing

Contributions are welcome. Feel free to fork the repo and submit a pull request.

---

## 📄 License

This project is open-source and available under the MIT License.

---

## 👤 Author

Developed by **Saintelus Pierre**

---
