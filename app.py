import os
import re
import json
import hashlib
import calendar
from io import BytesIO
from pathlib import Path
from datetime import date
import pandas as pd
import requests
import streamlit as st
import streamlit.components.v1 as components
import stripe
from supabase import create_client
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env", override=True)

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")  # optional here, not required for webhook verification

endpoint_secret = os.getenv("STRIPE_WEBHOOK_SECRET")

try:
    import stripe
except Exception:
    stripe = None

try:
    from openai import OpenAI
except Exception:
    OpenAI = None

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
except Exception:
    SimpleDocTemplate = None
    Paragraph = None
    Spacer = None
    getSampleStyleSheet = None
    letter = None

st.set_page_config(page_title="ExplainMyBudget AI", page_icon="💰", layout="wide")

if "language" not in st.session_state:
    st.session_state["language"] = "English"

try:
    from supabase import create_client
except Exception:
    create_client = None


FREE_PLAN = "free"
PREMIUM_PLAN = "premium"

APP_NAME = "ExplainMyBudget"

def get_supabase_client():
    if create_client is None:
        return None

    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_ANON_KEY")

    if not url or not key:
        return None

    return create_client(url, key)

def sync_premium_from_supabase(email):
    if not email:
        return False

    supabase = get_supabase_client()
    if supabase is None:
        return False

    try:
        profile = (
            supabase.table("user_profiles")
            .select("is_premium")
            .eq("email", email.lower().strip())
            .eq("app", APP_NAME)
            .execute()
        )

        if profile.data and profile.data[0].get("is_premium"):
            st.session_state["user_plan"] = PREMIUM_PLAN
            return True

    except Exception:
        return False

SUPPORTED_CURRENCIES = {
    "USD": {"symbol": "$", "name": "US Dollar"},
    "EUR": {"symbol": "€", "name": "Euro"},
    "GBP": {"symbol": "£", "name": "British Pound"},
    "CAD": {"symbol": "C$", "name": "Canadian Dollar"},
    "NGN": {"symbol": "₦", "name": "Nigerian Naira"},
    "INR": {"symbol": "₹", "name": "Indian Rupee"},
    "BRL": {"symbol": "R$", "name": "Brazilian Real"},
    "HTG": {"symbol": "G", "name": "Haitian Gourde"},
    "MXN": {"symbol": "Mex$", "name": "Mexican Peso"},
    "ZAR": {"symbol": "R", "name": "South African Rand"},
    "JPY": {"symbol": "¥", "name": "Japanese Yen"},
}

COUNTRY_CONTEXT = {
    "USD": "Typical expenses may include rent, groceries, insurance, subscriptions, transportation, and debt payments.",
    "EUR": "Typical expenses may include rent, utilities, transportation, groceries, insurance, and savings contributions.",
    "GBP": "Typical expenses may include rent, council tax, transport, groceries, utilities, and savings.",
    "CAD": "Typical expenses may include rent, groceries, transport, insurance, utilities, and savings.",
    "NGN": "Typical expenses may include food, transport, utilities, mobile data, family support, and savings.",
    "INR": "Typical expenses may include household costs, family support, transport, education, mobile data, and savings.",
    "BRL": "Typical expenses may include rent, food, transportation, utilities, installment payments, and savings.",
    "HTG": "Typical expenses may include food, transportation, school costs, family support, utilities, and savings.",
    "MXN": "Typical expenses may include rent, food, transport, utilities, family support, and installment payments.",
    "ZAR": "Typical expenses may include rent, food, transport, electricity, mobile data, debt payments, and savings.",
    "JPY": "Typical expenses may include rent, transportation, food, utilities, insurance, and savings.",
}

LANGUAGES = ["English", "French", "Spanish", "Hindi", "Haitian Creole", "Mandarin Chinese", "Standard Arabic", "Bengali", "Portuguese", "Urdu", "Russian"]

# Add more phrases over time. Unknown labels safely fall back to English.
TRANSLATIONS = {
    "French": {
        "Global Control": "Contrôle global", "Language": "Langue", "Display Currency": "Devise d'affichage",
        "Base Currency": "Devise de base", "Choose Section": "Choisir une section", "Planning Tools": "Outils de planification",
        "AI Tools": "Outils IA", "Reports": "Rapports", "Wealth Tools": "Outils de patrimoine", "Settings": "Paramètres",
        "Reset & Cleanup": "Réinitialisation et nettoyage", "Clear Expenses": "Effacer les dépenses", "Reset App": "Réinitialiser l'application",
        "Expenses cleared.": "Dépenses effacées.", "App reset complete.": "Réinitialisation terminée.", "Premium": "Premium",
        "Free Plan": "Forfait gratuit", "Budget Overview": "Aperçu du budget", "Financial Overview": "Vue d'ensemble financière",
        "Total Budget": "Budget total", "Total Spent": "Total dépensé", "Remaining": "Restant", "Income Snapshot": "Aperçu du revenu",
        "Income Left": "Revenu restant", "Savings Rate": "Taux d'épargne", "Financial Health Score": "Score de santé financière",
        "Category Summary": "Résumé par catégorie", "Smart Alerts Center": "Centre d'alertes intelligentes",
        "No budget yet. Go to Budget Planner first.": "Aucun budget pour le moment. Allez d'abord dans Planificateur de budget.",
        "Set Monthly Budget": "Définir le budget mensuel", "Quick Start Budget Templates": "Modèles de budget de démarrage rapide",
        "Load Basic Monthly Categories": "Charger les catégories mensuelles de base", "Default budget categories loaded.": "Catégories budgétaires par défaut chargées.",
        "Edit Budget Categories": "Modifier les catégories de budget", "Duplicate categories detected. Please fix them.": "Catégories en double détectées. Veuillez les corriger.",
        "Add One Budget Category": "Ajouter une catégorie de budget", "Category": "Catégorie", "Planned Amount": "Montant prévu",
        "Add Budget": "Ajouter un budget", "Budget added.": "Budget ajouté.", "Track Expenses": "Suivi des dépenses",
        "Create budget categories first.": "Créez d'abord des catégories de budget.", "Date": "Date", "Description": "Description",
        "Amount": "Montant", "Add Expense": "Ajouter une dépense", "Expense added.": "Dépense ajoutée.",
        "Monthly Income": "Revenu mensuel", "Enter your monthly income": "Entrez votre revenu mensuel", "Save Income": "Enregistrer le revenu",
        "Monthly income saved.": "Revenu mensuel enregistré.", "Current saved income": "Revenu enregistré actuel",
        "Savings Goal": "Objectif d'épargne", "How much do you want to save this month?": "Combien voulez-vous économiser ce mois-ci ?",
        "Save Goal": "Enregistrer l'objectif", "Savings goal saved.": "Objectif d'épargne enregistré.", "Current savings goal": "Objectif d'épargne actuel",
        "Can I Afford This?": "Puis-je me le permettre ?", "Enter amount you want to spend": "Entrez le montant que vous voulez dépenser",
        "Decision": "Décision", "Summary": "Résumé", "Please set your income first.": "Veuillez d'abord définir votre revenu.",
        "Spending Pattern Detection": "Détection des habitudes de dépenses", "Top Spending Categories": "Principales catégories de dépenses",
        "Smart Insight": "Aperçu intelligent", "Spending Trends Over Time": "Tendances des dépenses dans le temps",
        "Daily Spending": "Dépenses quotidiennes", "Trend Insight": "Aperçu de tendance", "Data Report": "Rapport de données",
        "Report Preview": "Aperçu du rapport", "Download Data Report": "Télécharger le rapport de données",
        "AI Insights Report": "Rapport d'analyses IA", "Generate Real AI Response": "Générer une réponse IA réelle",
        "Budget Doctor": "Docteur du budget", "Diagnosis": "Diagnostic", "Context": "Contexte",
        "Smart Recommendation": "Recommandation intelligente", "What Changed This Month?": "Qu'est-ce qui a changé ce mois-ci ?",
        "Ask Your Money AI": "Demandez à votre IA financière", "Ask a money question": "Posez une question financière",
        "AI Answer": "Réponse IA", "Your Money Personality": "Votre personnalité financière", "Analysis": "Analyse",
        "Your Type": "Votre profil", "Recommendation": "Recommandation", "Backup & Restore": "Sauvegarde et restauration",
        "Money Rewards": "Récompenses financières", "Shareable Money Snapshot": "Aperçu financier partageable",
        "AI Money Coach": "Coach financier IA", "Net Worth Tracker": "Suivi de la valeur nette",
        "Bill Reminder Center": "Centre de rappels de factures", "Upgrade Your Experience": "Améliorez votre expérience",
        "Premium Features": "Fonctionnalités Premium", "Pricing": "Tarification", "Upgrade Monthly": "Passer au mensuel",
        "Upgrade Yearly": "Passer à l'annuel", "Activate Premium Demo": "Activer la démo Premium",
        "Language, currency, tools, and plan": "Langue, devise, outils et forfait",
        "💰 ExplainMyBudget AI": "💰 ExplainMyBudget AI",
        "Your money, clearly explained — budget smarter, spend wiser, and build financial confidence anywhere in the world.": "Votre argent, clairement expliqué — gérez mieux votre budget, dépensez plus intelligemment et gagnez en confiance financière partout dans le monde.",
        "Global currency": "Devise mondiale", "AI-style insights": "Analyses de style IA", "Rewards": "Récompenses", "Mobile-ready": "Prêt pour mobile",
        "Plan": "Forfait", "Excellent financial health": "Excellente santé financière", "Good financial health": "Bonne santé financière",
        "Caution zone": "Zone de prudence", "High financial risk": "Risque financier élevé", "Budget exceeded by": "Budget dépassé de",
        "Immediate adjustment recommended.": "Ajustement immédiat recommandé.", "You have used": "Vous avez utilisé", "of this budget.": "de ce budget.",
        "Slow down before exceeding your limit.": "Ralentissez avant de dépasser votre limite.", "Forecast shows possible overspending.": "La prévision indique un risque de dépassement.",
        "Projected overage": "Dépassement prévu", "Global Context": "Contexte global", "Add Bill": "Ajouter une facture", "Bill Name": "Nom de la facture",
        "Due Date": "Date d'échéance", "Bill Amount": "Montant de la facture", "Already Paid?": "Déjà payé ?", "Bill added.": "Facture ajoutée.",
        "Bills": "Factures", "No bills added yet.": "Aucune facture ajoutée pour le moment.", "Bill Status": "État des factures", "Paid": "Payé",
        "Overdue by": "En retard de", "days": "jours", "Due in": "Échéance dans", "Add your budget categories first.": "Ajoutez d'abord vos catégories de budget.",
        "Spending Breakdown": "Répartition des dépenses", "Smart Explanation": "Explication intelligente", "Suggested Next Move": "Prochaine action suggérée",
        "Forecasting Engine": "Moteur de prévision", "Data Report Download": "Téléchargement du rapport de données", "Advanced Insights": "Analyses avancées",
        "Smart Savings Guidance": "Conseils intelligents d'épargne", "Global money context": "Contexte financier mondial",
    },
    "Spanish": {
        "Global Control": "Control global", "Language": "Idioma", "Display Currency": "Moneda visible",
        "Base Currency": "Moneda base", "Choose Section": "Elegir sección", "Budget Overview": "Resumen del presupuesto",
        "Monthly Income": "Ingreso mensual", "Track Expenses": "Seguimiento de gastos", "Savings Goal": "Meta de ahorro",
        "Data Report": "Informe de datos", "Category": "Categoría", "Amount": "Monto", "Date": "Fecha",
        "Description": "Descripción", "Add Expense": "Agregar gasto", "Add Budget": "Agregar presupuesto",
        "Save Income": "Guardar ingreso", "Save Goal": "Guardar meta", "Can I Afford This?": "¿Puedo pagarlo?",
        "Decision": "Decisión", "Summary": "Resumen", "AI Insights Report": "Informe de IA",
        "Budget Doctor": "Doctor del presupuesto", "Ask Your Money AI": "Pregunta a tu IA financiera",
        "Money Rewards": "Recompensas financieras", "Net Worth Tracker": "Seguimiento del patrimonio neto",
        "Bill Reminder Center": "Centro de recordatorios de facturas", "Upgrade Your Experience": "Mejora tu experiencia",
        "Premium Features": "Funciones Premium", "Pricing": "Precio", "Upgrade Monthly": "Actualizar mensual",
        "Upgrade Yearly": "Actualizar anual", "Activate Premium Demo": "Activar demo Premium",
    },
    "Hindi": {
        "Global Control": "वैश्विक नियंत्रण", "Language": "भाषा", "Display Currency": "प्रदर्शन मुद्रा",
        "Base Currency": "आधार मुद्रा", "Choose Section": "सेक्शन चुनें", "Budget Overview": "बजट अवलोकन",
        "Monthly Income": "मासिक आय", "Track Expenses": "खर्च ट्रैक करें", "Savings Goal": "बचत लक्ष्य",
        "Data Report": "डेटा रिपोर्ट", "Category": "श्रेणी", "Amount": "राशि", "Date": "तारीख",
        "Description": "विवरण", "Add Expense": "खर्च जोड़ें", "Add Budget": "बजट जोड़ें",
        "Save Income": "आय सहेजें", "Save Goal": "लक्ष्य सहेजें", "Can I Afford This?": "क्या मैं यह खरीद सकता हूँ?",
        "Decision": "निर्णय", "Summary": "सारांश", "AI Insights Report": "AI इनसाइट रिपोर्ट",
        "Budget Doctor": "बजट डॉक्टर", "Ask Your Money AI": "अपने पैसे AI से पूछें",
        "Money Rewards": "मनी रिवॉर्ड्स", "Net Worth Tracker": "नेट वर्थ ट्रैकर",
        "Bill Reminder Center": "बिल रिमाइंडर सेंटर", "Upgrade Your Experience": "अपना अनुभव अपग्रेड करें",
        "Premium Features": "प्रीमियम सुविधाएँ", "Pricing": "मूल्य", "Upgrade Monthly": "मासिक अपग्रेड",
        "Upgrade Yearly": "वार्षिक अपग्रेड", "Activate Premium Demo": "प्रीमियम डेमो सक्रिय करें",
    },
    "Haitian Creole": {
        "Global Control": "Kontwòl global", "Language": "Lang", "Display Currency": "Lajan pou montre",
        "Base Currency": "Lajan debaz", "Choose Section": "Chwazi seksyon", "Budget Overview": "Apèsi bidjè",
        "Monthly Income": "Revni chak mwa", "Track Expenses": "Swiv depans yo", "Savings Goal": "Objektif ekonomi",
        "Data Report": "Rapò done", "Category": "Kategori", "Amount": "Kantite", "Date": "Dat",
        "Description": "Deskripsyon", "Add Expense": "Ajoute depans", "Add Budget": "Ajoute bidjè",
        "Save Income": "Sove revni", "Save Goal": "Sove objektif", "Can I Afford This?": "Èske mwen ka peye sa?",
        "Decision": "Desizyon", "Summary": "Rezime", "AI Insights Report": "Rapò analiz IA",
        "Budget Doctor": "Doktè bidjè", "Ask Your Money AI": "Mande IA lajan ou",
        "Money Rewards": "Rekonpans lajan", "Net Worth Tracker": "Swivi valè nèt",
        "Bill Reminder Center": "Sant rapèl fakti", "Upgrade Your Experience": "Amelyore eksperyans ou",
        "Premium Features": "Fonksyon Premium", "Pricing": "Pri", "Upgrade Monthly": "Upgrade chak mwa",
        "Upgrade Yearly": "Upgrade chak ane", "Activate Premium Demo": "Aktive demo Premium",
    },
}

# Extra translation keys used by account access, saved budgets, and PDF export.
TRANSLATIONS.setdefault("French", {}).update({
    "Account Access": "Accès au compte", "Sign In": "Se connecter", "Create Account": "Créer un compte", "Forgot Password?": "Mot de passe oublié ?", "Upgrade to Premium": "Passer à Premium",
    "Email": "E-mail", "Password": "Mot de passe", "Signed in as": "Connecté en tant que",
    "Save Budget": "Enregistrer le budget", "Load Budget": "Charger le budget", "Sign Out": "Se déconnecter",
    "Signed out.": "Déconnecté.", "Signed in successfully.": "Connexion réussie.",
    "Invalid email or password.": "E-mail ou mot de passe invalide.", "Enter a valid email address.": "Entrez une adresse e-mail valide.",
    "Password must be at least 6 characters.": "Le mot de passe doit contenir au moins 6 caractères.",
    "This account already exists.": "Ce compte existe déjà.", "Account created and budget saved.": "Compte créé et budget enregistré.",
    "Please sign in first.": "Veuillez d'abord vous connecter.", "Budget saved to your account.": "Budget enregistré dans votre compte.",
    "Saved budget loaded.": "Budget enregistré chargé.", "No saved budget found for this account yet.": "Aucun budget enregistré trouvé pour ce compte pour le moment.",
    "Saved budget could not be loaded.": "Le budget enregistré n'a pas pu être chargé.", "Download PDF Report": "Télécharger le rapport PDF",
    "PDF export needs ReportLab. Install it with: pip install reportlab": "L'export PDF nécessite ReportLab. Installez-le avec : pip install reportlab",
    "Show password": "Afficher le mot de passe",
    "Show or hide password": "Afficher ou masquer le mot de passe",
    "Enter your password": "Entrez votre mot de passe",
    "Create a password": "Créez un mot de passe",
    "Password reset is not connected yet. For now, create a new account or contact support.": "La réinitialisation du mot de passe n'est pas encore connectée. Pour l'instant, créez un nouveau compte ou contactez le support.",
})

TRANSLATIONS.setdefault("French", {}).update({
    "Start 1 Free Trial": "Commencer 1 essai gratuit",
    "Your free trial is active. Premium tools are unlocked for this session.": "Votre essai gratuit est actif. Les outils Premium sont débloqués pour cette session.",
    "Your free trial has already been used. Upgrade to continue.": "Votre essai gratuit a déjà été utilisé. Passez à Premium pour continuer.",
})

# Additional global language packs for expanded UI coverage.
# These static packs cover the most common sidebar, account, dashboard, button,
# alert, and report labels. Any missing text still falls back to AI translation
# through t(...), as long as OPENAI_API_KEY is available.
ADDITIONAL_LANGUAGE_PACKS = {
    "Mandarin Chinese": {
        "Global Control": "全局控制", "Language": "语言", "Display Currency": "显示货币", "Base Currency": "基础货币", "Choose Section": "选择部分",
        "Planning Tools": "规划工具", "AI Tools": "AI 工具", "Reports": "报告", "Wealth Tools": "财富工具", "Settings": "设置",
        "Reset & Cleanup": "重置和清理", "Clear Expenses": "清除支出", "Reset App": "重置应用", "Expenses cleared.": "支出已清除。", "App reset complete.": "应用重置完成。",
        "Premium": "高级版", "Free Plan": "免费计划", "Plan": "计划", "Upgrade to Premium": "升级到高级版", "Upgrade Your Experience": "升级你的体验",
        "Premium Features": "高级功能", "Pricing": "价格", "Upgrade Monthly": "按月升级", "Upgrade Yearly": "按年升级", "Activate Premium Demo": "启用高级版演示",
        "Account Access": "账户访问", "Sign In": "登录", "Create Account": "创建账户", "Forgot Password?": "忘记密码？", "Show password": "显示密码", "Show or hide password": "显示或隐藏密码",
        "Email": "电子邮件", "Password": "密码", "Enter your password": "输入你的密码", "Create a password": "创建密码", "Signed in as": "已登录为",
        "Save Budget": "保存预算", "Load Budget": "加载预算", "Sign Out": "退出登录", "Signed out.": "已退出登录。", "Signed in successfully.": "登录成功。",
        "Invalid email or password.": "电子邮件或密码无效。", "Enter a valid email address.": "请输入有效的电子邮件地址。", "Password must be at least 6 characters.": "密码至少需要 6 个字符。",
        "This account already exists.": "该账户已存在。", "Account created and budget saved.": "账户已创建，预算已保存。", "Please sign in first.": "请先登录。",
        "Budget saved to your account.": "预算已保存到你的账户。", "Saved budget loaded.": "已加载保存的预算。", "No saved budget found for this account yet.": "此账户尚未找到保存的预算。",
        "Saved budget could not be loaded.": "无法加载保存的预算。", "Password reset is not connected yet. For now, create a new account or contact support.": "密码重置功能尚未连接。暂时请创建新账户或联系支持。",
        "Budget Overview": "预算概览", "Financial Overview": "财务概览", "Total Budget": "总预算", "Total Spent": "总支出", "Remaining": "剩余", "Income Snapshot": "收入快照",
        "Income Left": "剩余收入", "Savings Rate": "储蓄率", "Financial Health Score": "财务健康评分", "Category Summary": "分类摘要", "Smart Alerts Center": "智能提醒中心",
        "No budget yet. Go to Budget Planner first.": "还没有预算。请先前往预算规划器。", "Set Monthly Budget": "设置月度预算", "Quick Start Budget Templates": "快速预算模板",
        "Load Basic Monthly Categories": "加载基础月度分类", "Default budget categories loaded.": "默认预算分类已加载。", "Edit Budget Categories": "编辑预算分类",
        "Duplicate categories detected. Please fix them.": "检测到重复分类。请修正。", "Add One Budget Category": "添加一个预算分类", "Category": "分类", "Planned Amount": "计划金额",
        "Add Budget": "添加预算", "Budget added.": "预算已添加。", "Track Expenses": "跟踪支出", "Create budget categories first.": "请先创建预算分类。", "Date": "日期", "Description": "描述",
        "Amount": "金额", "Add Expense": "添加支出", "Expense added.": "支出已添加。", "Monthly Income": "月收入", "Enter your monthly income": "输入你的月收入", "Save Income": "保存收入",
        "Monthly income saved.": "月收入已保存。", "Current saved income": "当前保存的收入", "Savings Goal": "储蓄目标", "How much do you want to save this month?": "你这个月想存多少钱？",
        "Save Goal": "保存目标", "Savings goal saved.": "储蓄目标已保存。", "Current savings goal": "当前储蓄目标", "Can I Afford This?": "我负担得起吗？", "Enter amount you want to spend": "输入你想花费的金额",
        "Decision": "决定", "Summary": "摘要", "Please set your income first.": "请先设置你的收入。", "Quick Actions": "快速操作", "Jump straight into the tools people use most.": "直接进入最常用的工具。",
        "Start your money command center": "开始你的资金控制中心", "No budget yet. Use the quick actions below to build your first monthly plan.": "还没有预算。使用下面的快速操作创建你的第一个月度计划。",
        "Step 1: Build your budget": "第 1 步：创建预算", "Step 2: Track expenses": "第 2 步：跟踪支出", "Step 3: Get guidance": "第 3 步：获取指导", "Load starter categories": "加载入门分类",
        "Go to income": "前往收入", "Open upgrade": "打开升级", "AI Command Center": "AI 控制中心", "Next best move": "下一步最佳行动", "Budget Burn": "预算消耗", "Top Spend": "最高支出", "Runway": "资金余量",
        "Healthy": "健康", "Tight": "紧张", "Over budget": "超出预算", "Savings risk": "储蓄风险", "Dashboard": "仪表板", "Budget": "预算", "Expenses": "支出", "Income": "收入", "Bills": "账单", "Coach": "教练", "Report": "报告", "Upgrade": "升级",
        "Data Report": "数据报告", "Download Data Report": "下载数据报告", "Download PDF Report": "下载 PDF 报告", "AI Insights Report": "AI 洞察报告", "Generate Real AI Response": "生成真实 AI 回复",
        "Budget Doctor": "预算医生", "Diagnosis": "诊断", "Context": "背景", "Smart Recommendation": "智能建议", "Ask Your Money AI": "询问你的理财 AI", "Ask a money question": "提出理财问题", "AI Answer": "AI 回答",
        "Net Worth Tracker": "净资产跟踪器", "Bill Reminder Center": "账单提醒中心", "Add Bill": "添加账单", "Bill Name": "账单名称", "Due Date": "到期日", "Bill Amount": "账单金额", "Already Paid?": "已付款？", "Bill added.": "账单已添加。", "Paid": "已付款",
    },
    "Standard Arabic": {
        "Global Control": "التحكم العام", "Language": "اللغة", "Display Currency": "عملة العرض", "Base Currency": "العملة الأساسية", "Choose Section": "اختر القسم",
        "Planning Tools": "أدوات التخطيط", "AI Tools": "أدوات الذكاء الاصطناعي", "Reports": "التقارير", "Wealth Tools": "أدوات الثروة", "Settings": "الإعدادات",
        "Reset & Cleanup": "إعادة التعيين والتنظيف", "Clear Expenses": "مسح المصروفات", "Reset App": "إعادة تعيين التطبيق", "Expenses cleared.": "تم مسح المصروفات.", "App reset complete.": "اكتملت إعادة تعيين التطبيق.",
        "Premium": "مميز", "Free Plan": "الخطة المجانية", "Plan": "الخطة", "Upgrade to Premium": "الترقية إلى المميز", "Upgrade Your Experience": "طوّر تجربتك",
        "Premium Features": "ميزات مميزة", "Pricing": "الأسعار", "Upgrade Monthly": "ترقية شهرية", "Upgrade Yearly": "ترقية سنوية", "Activate Premium Demo": "تفعيل العرض التجريبي المميز",
        "Account Access": "الوصول إلى الحساب", "Sign In": "تسجيل الدخول", "Create Account": "إنشاء حساب", "Forgot Password?": "هل نسيت كلمة المرور؟", "Show password": "إظهار كلمة المرور", "Show or hide password": "إظهار أو إخفاء كلمة المرور",
        "Email": "البريد الإلكتروني", "Password": "كلمة المرور", "Enter your password": "أدخل كلمة المرور", "Create a password": "أنشئ كلمة مرور", "Signed in as": "تم تسجيل الدخول باسم",
        "Save Budget": "حفظ الميزانية", "Load Budget": "تحميل الميزانية", "Sign Out": "تسجيل الخروج", "Signed out.": "تم تسجيل الخروج.", "Signed in successfully.": "تم تسجيل الدخول بنجاح.",
        "Invalid email or password.": "البريد الإلكتروني أو كلمة المرور غير صحيحة.", "Enter a valid email address.": "أدخل بريدًا إلكترونيًا صالحًا.", "Password must be at least 6 characters.": "يجب أن تكون كلمة المرور 6 أحرف على الأقل.",
        "This account already exists.": "هذا الحساب موجود بالفعل.", "Account created and budget saved.": "تم إنشاء الحساب وحفظ الميزانية.", "Please sign in first.": "يرجى تسجيل الدخول أولاً.",
        "Budget saved to your account.": "تم حفظ الميزانية في حسابك.", "Saved budget loaded.": "تم تحميل الميزانية المحفوظة.", "No saved budget found for this account yet.": "لا توجد ميزانية محفوظة لهذا الحساب حتى الآن.",
        "Saved budget could not be loaded.": "تعذر تحميل الميزانية المحفوظة.", "Password reset is not connected yet. For now, create a new account or contact support.": "إعادة تعيين كلمة المرور غير متصلة بعد. في الوقت الحالي، أنشئ حسابًا جديدًا أو تواصل مع الدعم.",
        "Budget Overview": "نظرة عامة على الميزانية", "Financial Overview": "نظرة عامة مالية", "Total Budget": "إجمالي الميزانية", "Total Spent": "إجمالي المصروف", "Remaining": "المتبقي", "Income Snapshot": "لمحة عن الدخل",
        "Income Left": "الدخل المتبقي", "Savings Rate": "معدل الادخار", "Financial Health Score": "درجة الصحة المالية", "Category Summary": "ملخص الفئات", "Smart Alerts Center": "مركز التنبيهات الذكية",
        "No budget yet. Go to Budget Planner first.": "لا توجد ميزانية بعد. اذهب أولاً إلى مخطط الميزانية.", "Set Monthly Budget": "تحديد الميزانية الشهرية", "Quick Start Budget Templates": "قوالب ميزانية سريعة",
        "Load Basic Monthly Categories": "تحميل الفئات الشهرية الأساسية", "Default budget categories loaded.": "تم تحميل فئات الميزانية الافتراضية.", "Edit Budget Categories": "تعديل فئات الميزانية",
        "Duplicate categories detected. Please fix them.": "تم اكتشاف فئات مكررة. يرجى إصلاحها.", "Add One Budget Category": "إضافة فئة ميزانية واحدة", "Category": "الفئة", "Planned Amount": "المبلغ المخطط",
        "Add Budget": "إضافة ميزانية", "Budget added.": "تمت إضافة الميزانية.", "Track Expenses": "تتبع المصروفات", "Create budget categories first.": "أنشئ فئات الميزانية أولاً.", "Date": "التاريخ", "Description": "الوصف",
        "Amount": "المبلغ", "Add Expense": "إضافة مصروف", "Expense added.": "تمت إضافة المصروف.", "Monthly Income": "الدخل الشهري", "Enter your monthly income": "أدخل دخلك الشهري", "Save Income": "حفظ الدخل",
        "Monthly income saved.": "تم حفظ الدخل الشهري.", "Current saved income": "الدخل المحفوظ الحالي", "Savings Goal": "هدف الادخار", "How much do you want to save this month?": "كم تريد أن تدخر هذا الشهر؟",
        "Save Goal": "حفظ الهدف", "Savings goal saved.": "تم حفظ هدف الادخار.", "Current savings goal": "هدف الادخار الحالي", "Can I Afford This?": "هل أستطيع تحمل هذا؟", "Enter amount you want to spend": "أدخل المبلغ الذي تريد إنفاقه",
        "Decision": "القرار", "Summary": "الملخص", "Please set your income first.": "يرجى تحديد دخلك أولاً.", "Quick Actions": "إجراءات سريعة", "Jump straight into the tools people use most.": "انتقل مباشرة إلى الأدوات الأكثر استخدامًا.",
        "Start your money command center": "ابدأ مركز التحكم المالي", "No budget yet. Use the quick actions below to build your first monthly plan.": "لا توجد ميزانية بعد. استخدم الإجراءات السريعة أدناه لبناء أول خطة شهرية.",
        "Step 1: Build your budget": "الخطوة 1: ابنِ ميزانيتك", "Step 2: Track expenses": "الخطوة 2: تتبع المصروفات", "Step 3: Get guidance": "الخطوة 3: احصل على إرشاد", "Load starter categories": "تحميل فئات البداية",
        "Go to income": "اذهب إلى الدخل", "Open upgrade": "فتح الترقية", "AI Command Center": "مركز تحكم الذكاء الاصطناعي", "Next best move": "أفضل خطوة تالية", "Budget Burn": "استهلاك الميزانية", "Top Spend": "أعلى إنفاق", "Runway": "الهامش المالي",
        "Healthy": "صحي", "Tight": "ضيق", "Over budget": "تجاوز الميزانية", "Savings risk": "خطر على الادخار", "Dashboard": "لوحة المعلومات", "Budget": "الميزانية", "Expenses": "المصروفات", "Income": "الدخل", "Bills": "الفواتير", "Coach": "المدرب", "Report": "التقرير", "Upgrade": "ترقية",
        "Data Report": "تقرير البيانات", "Download Data Report": "تنزيل تقرير البيانات", "Download PDF Report": "تنزيل تقرير PDF", "AI Insights Report": "تقرير رؤى الذكاء الاصطناعي", "Generate Real AI Response": "إنشاء رد ذكاء اصطناعي حقيقي",
        "Budget Doctor": "طبيب الميزانية", "Diagnosis": "التشخيص", "Context": "السياق", "Smart Recommendation": "توصية ذكية", "Ask Your Money AI": "اسأل ذكاءك المالي", "Ask a money question": "اطرح سؤالاً ماليًا", "AI Answer": "إجابة الذكاء الاصطناعي",
        "Net Worth Tracker": "متتبع صافي الثروة", "Bill Reminder Center": "مركز تذكير الفواتير", "Add Bill": "إضافة فاتورة", "Bill Name": "اسم الفاتورة", "Due Date": "تاريخ الاستحقاق", "Bill Amount": "مبلغ الفاتورة", "Already Paid?": "هل تم الدفع؟", "Bill added.": "تمت إضافة الفاتورة.", "Paid": "مدفوع",
    },
    "Bengali": {
        "Global Control": "গ্লোবাল কন্ট্রোল", "Language": "ভাষা", "Display Currency": "প্রদর্শনের মুদ্রা", "Base Currency": "মূল মুদ্রা", "Choose Section": "সেকশন নির্বাচন করুন",
        "AI Tools": "AI টুলস", "Reports": "রিপোর্ট", "Settings": "সেটিংস", "Premium": "প্রিমিয়াম", "Free Plan": "ফ্রি প্ল্যান", "Plan": "প্ল্যান", "Upgrade to Premium": "প্রিমিয়ামে আপগ্রেড করুন",
        "Account Access": "অ্যাকাউন্ট অ্যাক্সেস", "Sign In": "সাইন ইন", "Create Account": "অ্যাকাউন্ট তৈরি করুন", "Forgot Password?": "পাসওয়ার্ড ভুলে গেছেন?", "Show password": "পাসওয়ার্ড দেখান", "Show or hide password": "পাসওয়ার্ড দেখান বা লুকান",
        "Email": "ইমেইল", "Password": "পাসওয়ার্ড", "Enter your password": "আপনার পাসওয়ার্ড লিখুন", "Create a password": "একটি পাসওয়ার্ড তৈরি করুন", "Signed in as": "সাইন ইন করেছেন",
        "Save Budget": "বাজেট সংরক্ষণ করুন", "Load Budget": "বাজেট লোড করুন", "Sign Out": "সাইন আউট", "Signed out.": "সাইন আউট সম্পন্ন।", "Signed in successfully.": "সফলভাবে সাইন ইন হয়েছে।",
        "Invalid email or password.": "ইমেইল বা পাসওয়ার্ড ভুল।", "Enter a valid email address.": "একটি বৈধ ইমেইল ঠিকানা লিখুন।", "Password must be at least 6 characters.": "পাসওয়ার্ড কমপক্ষে ৬ অক্ষরের হতে হবে।",
        "This account already exists.": "এই অ্যাকাউন্টটি ইতিমধ্যে আছে।", "Account created and budget saved.": "অ্যাকাউন্ট তৈরি হয়েছে এবং বাজেট সংরক্ষণ হয়েছে।", "Please sign in first.": "প্রথমে সাইন ইন করুন।",
        "Password reset is not connected yet. For now, create a new account or contact support.": "পাসওয়ার্ড রিসেট এখনো সংযুক্ত নয়। আপাতত নতুন অ্যাকাউন্ট তৈরি করুন বা সাপোর্টে যোগাযোগ করুন।",
        "Budget Overview": "বাজেট ওভারভিউ", "Financial Overview": "আর্থিক ওভারভিউ", "Total Budget": "মোট বাজেট", "Total Spent": "মোট খরচ", "Remaining": "বাকি", "Income Snapshot": "আয়ের সারাংশ",
        "Income Left": "বাকি আয়", "Savings Rate": "সঞ্চয়ের হার", "Financial Health Score": "আর্থিক স্বাস্থ্য স্কোর", "Category Summary": "ক্যাটাগরি সারাংশ", "Smart Alerts Center": "স্মার্ট অ্যালার্ট সেন্টার",
        "Set Monthly Budget": "মাসিক বাজেট সেট করুন", "Quick Start Budget Templates": "দ্রুত বাজেট টেমপ্লেট", "Load Basic Monthly Categories": "প্রাথমিক মাসিক ক্যাটাগরি লোড করুন", "Default budget categories loaded.": "ডিফল্ট বাজেট ক্যাটাগরি লোড হয়েছে।",
        "Edit Budget Categories": "বাজেট ক্যাটাগরি সম্পাদনা করুন", "Add One Budget Category": "একটি বাজেট ক্যাটাগরি যোগ করুন", "Category": "ক্যাটাগরি", "Planned Amount": "পরিকল্পিত পরিমাণ", "Add Budget": "বাজেট যোগ করুন", "Budget added.": "বাজেট যোগ হয়েছে।",
        "Track Expenses": "খরচ ট্র্যাক করুন", "Create budget categories first.": "প্রথমে বাজেট ক্যাটাগরি তৈরি করুন।", "Date": "তারিখ", "Description": "বিবরণ", "Amount": "পরিমাণ", "Add Expense": "খরচ যোগ করুন", "Expense added.": "খরচ যোগ হয়েছে।",
        "Monthly Income": "মাসিক আয়", "Enter your monthly income": "আপনার মাসিক আয় লিখুন", "Save Income": "আয় সংরক্ষণ করুন", "Monthly income saved.": "মাসিক আয় সংরক্ষণ হয়েছে।", "Current saved income": "বর্তমান সংরক্ষিত আয়",
        "Savings Goal": "সঞ্চয়ের লক্ষ্য", "Save Goal": "লক্ষ্য সংরক্ষণ করুন", "Savings goal saved.": "সঞ্চয়ের লক্ষ্য সংরক্ষণ হয়েছে।", "Can I Afford This?": "আমি কি এটা বহন করতে পারব?", "Decision": "সিদ্ধান্ত", "Summary": "সারাংশ",
        "Quick Actions": "দ্রুত কাজ", "AI Command Center": "AI কমান্ড সেন্টার", "Next best move": "পরবর্তী সেরা পদক্ষেপ", "Dashboard": "ড্যাশবোর্ড", "Budget": "বাজেট", "Expenses": "খরচ", "Income": "আয়", "Bills": "বিল", "Coach": "কোচ", "Report": "রিপোর্ট", "Upgrade": "আপগ্রেড",
        "Data Report": "ডেটা রিপোর্ট", "Download Data Report": "ডেটা রিপোর্ট ডাউনলোড করুন", "Download PDF Report": "PDF রিপোর্ট ডাউনলোড করুন", "AI Insights Report": "AI ইনসাইট রিপোর্ট", "Budget Doctor": "বাজেট ডাক্তার", "Ask Your Money AI": "আপনার মানি AI-কে জিজ্ঞাসা করুন",
        "Bill Reminder Center": "বিল রিমাইন্ডার সেন্টার", "Add Bill": "বিল যোগ করুন", "Bill Name": "বিলের নাম", "Due Date": "শেষ তারিখ", "Bill Amount": "বিলের পরিমাণ", "Already Paid?": "ইতিমধ্যে পরিশোধিত?", "Bill added.": "বিল যোগ হয়েছে।", "Paid": "পরিশোধিত",
    },
    "Portuguese": {
        "Global Control": "Controle global", "Language": "Idioma", "Display Currency": "Moeda de exibição", "Base Currency": "Moeda base", "Choose Section": "Escolher seção", "AI Tools": "Ferramentas de IA", "Reports": "Relatórios", "Settings": "Configurações",
        "Premium": "Premium", "Free Plan": "Plano gratuito", "Plan": "Plano", "Upgrade to Premium": "Fazer upgrade para Premium", "Account Access": "Acesso à conta", "Sign In": "Entrar", "Create Account": "Criar conta", "Forgot Password?": "Esqueceu a senha?", "Show password": "Mostrar senha", "Show or hide password": "Mostrar ou ocultar senha",
        "Email": "E-mail", "Password": "Senha", "Enter your password": "Digite sua senha", "Create a password": "Crie uma senha", "Signed in as": "Conectado como", "Save Budget": "Salvar orçamento", "Load Budget": "Carregar orçamento", "Sign Out": "Sair", "Signed out.": "Você saiu.", "Signed in successfully.": "Login realizado com sucesso.",
        "Invalid email or password.": "E-mail ou senha inválidos.", "Enter a valid email address.": "Digite um endereço de e-mail válido.", "Password must be at least 6 characters.": "A senha deve ter pelo menos 6 caracteres.", "This account already exists.": "Esta conta já existe.", "Account created and budget saved.": "Conta criada e orçamento salvo.", "Please sign in first.": "Faça login primeiro.",
        "Password reset is not connected yet. For now, create a new account or contact support.": "A redefinição de senha ainda não está conectada. Por enquanto, crie uma nova conta ou entre em contato com o suporte.",
        "Budget Overview": "Visão geral do orçamento", "Financial Overview": "Visão financeira", "Total Budget": "Orçamento total", "Total Spent": "Total gasto", "Remaining": "Restante", "Income Snapshot": "Resumo da renda", "Income Left": "Renda restante", "Savings Rate": "Taxa de poupança", "Financial Health Score": "Pontuação de saúde financeira", "Category Summary": "Resumo por categoria", "Smart Alerts Center": "Central de alertas inteligentes",
        "Set Monthly Budget": "Definir orçamento mensal", "Quick Start Budget Templates": "Modelos rápidos de orçamento", "Load Basic Monthly Categories": "Carregar categorias mensais básicas", "Default budget categories loaded.": "Categorias padrão carregadas.", "Edit Budget Categories": "Editar categorias do orçamento", "Category": "Categoria", "Planned Amount": "Valor planejado", "Add Budget": "Adicionar orçamento", "Budget added.": "Orçamento adicionado.",
        "Track Expenses": "Controlar despesas", "Date": "Data", "Description": "Descrição", "Amount": "Valor", "Add Expense": "Adicionar despesa", "Expense added.": "Despesa adicionada.", "Monthly Income": "Renda mensal", "Enter your monthly income": "Digite sua renda mensal", "Save Income": "Salvar renda", "Monthly income saved.": "Renda mensal salva.", "Current saved income": "Renda salva atual",
        "Savings Goal": "Meta de poupança", "Save Goal": "Salvar meta", "Savings goal saved.": "Meta de poupança salva.", "Can I Afford This?": "Posso pagar por isso?", "Decision": "Decisão", "Summary": "Resumo", "Quick Actions": "Ações rápidas", "AI Command Center": "Central de comando de IA", "Next best move": "Próxima melhor ação", "Dashboard": "Painel", "Budget": "Orçamento", "Expenses": "Despesas", "Income": "Renda", "Bills": "Contas", "Coach": "Coach", "Report": "Relatório", "Upgrade": "Upgrade",
        "Data Report": "Relatório de dados", "Download Data Report": "Baixar relatório de dados", "Download PDF Report": "Baixar relatório PDF", "AI Insights Report": "Relatório de insights de IA", "Budget Doctor": "Doutor do orçamento", "Ask Your Money AI": "Pergunte à sua IA financeira", "Bill Reminder Center": "Central de lembretes de contas", "Add Bill": "Adicionar conta", "Bill Name": "Nome da conta", "Due Date": "Data de vencimento", "Bill Amount": "Valor da conta", "Already Paid?": "Já pago?", "Bill added.": "Conta adicionada.", "Paid": "Pago",
    },
    "Urdu": {
        "Global Control": "عالمی کنٹرول", "Language": "زبان", "Display Currency": "دکھائی جانے والی کرنسی", "Base Currency": "بنیادی کرنسی", "Choose Section": "سیکشن منتخب کریں", "AI Tools": "AI ٹولز", "Reports": "رپورٹس", "Settings": "ترتیبات",
        "Premium": "پریمیم", "Free Plan": "مفت پلان", "Plan": "پلان", "Upgrade to Premium": "پریمیم میں اپ گریڈ کریں", "Account Access": "اکاؤنٹ تک رسائی", "Sign In": "سائن ان", "Create Account": "اکاؤنٹ بنائیں", "Forgot Password?": "پاس ورڈ بھول گئے؟", "Show password": "پاس ورڈ دکھائیں", "Show or hide password": "پاس ورڈ دکھائیں یا چھپائیں",
        "Email": "ای میل", "Password": "پاس ورڈ", "Enter your password": "اپنا پاس ورڈ درج کریں", "Create a password": "پاس ورڈ بنائیں", "Signed in as": "سائن ان بطور", "Save Budget": "بجٹ محفوظ کریں", "Load Budget": "بجٹ لوڈ کریں", "Sign Out": "سائن آؤٹ", "Signed out.": "سائن آؤٹ ہوگیا۔", "Signed in successfully.": "کامیابی سے سائن ان ہوگیا۔",
        "Invalid email or password.": "ای میل یا پاس ورڈ غلط ہے۔", "Enter a valid email address.": "درست ای میل ایڈریس درج کریں۔", "Password must be at least 6 characters.": "پاس ورڈ کم از کم 6 حروف کا ہونا چاہیے۔", "This account already exists.": "یہ اکاؤنٹ پہلے سے موجود ہے۔", "Account created and budget saved.": "اکاؤنٹ بن گیا اور بجٹ محفوظ ہوگیا۔", "Please sign in first.": "براہ کرم پہلے سائن ان کریں۔",
        "Password reset is not connected yet. For now, create a new account or contact support.": "پاس ورڈ ری سیٹ ابھی منسلک نہیں ہے۔ فی الحال نیا اکاؤنٹ بنائیں یا سپورٹ سے رابطہ کریں۔",
        "Budget Overview": "بجٹ کا جائزہ", "Financial Overview": "مالی جائزہ", "Total Budget": "کل بجٹ", "Total Spent": "کل خرچ", "Remaining": "باقی", "Income Snapshot": "آمدنی کا خلاصہ", "Income Left": "باقی آمدنی", "Savings Rate": "بچت کی شرح", "Financial Health Score": "مالی صحت کا اسکور", "Category Summary": "زمرہ خلاصہ", "Smart Alerts Center": "سمارٹ الرٹس سینٹر",
        "Set Monthly Budget": "ماہانہ بجٹ سیٹ کریں", "Quick Start Budget Templates": "فوری بجٹ ٹیمپلیٹس", "Load Basic Monthly Categories": "بنیادی ماہانہ زمرے لوڈ کریں", "Default budget categories loaded.": "ڈیفالٹ بجٹ زمرے لوڈ ہوگئے۔", "Edit Budget Categories": "بجٹ زمرے ترمیم کریں", "Category": "زمرہ", "Planned Amount": "منصوبہ بند رقم", "Add Budget": "بجٹ شامل کریں", "Budget added.": "بجٹ شامل ہوگیا۔",
        "Track Expenses": "خرچ ٹریک کریں", "Date": "تاریخ", "Description": "تفصیل", "Amount": "رقم", "Add Expense": "خرچ شامل کریں", "Expense added.": "خرچ شامل ہوگیا۔", "Monthly Income": "ماہانہ آمدنی", "Enter your monthly income": "اپنی ماہانہ آمدنی درج کریں", "Save Income": "آمدنی محفوظ کریں", "Monthly income saved.": "ماہانہ آمدنی محفوظ ہوگئی۔", "Current saved income": "موجودہ محفوظ آمدنی",
        "Savings Goal": "بچت کا ہدف", "Save Goal": "ہدف محفوظ کریں", "Savings goal saved.": "بچت کا ہدف محفوظ ہوگیا۔", "Can I Afford This?": "کیا میں یہ برداشت کر سکتا ہوں؟", "Decision": "فیصلہ", "Summary": "خلاصہ", "Quick Actions": "فوری اقدامات", "AI Command Center": "AI کمانڈ سینٹر", "Next best move": "اگلا بہترین قدم", "Dashboard": "ڈیش بورڈ", "Budget": "بجٹ", "Expenses": "اخراجات", "Income": "آمدنی", "Bills": "بل", "Coach": "کوچ", "Report": "رپورٹ", "Upgrade": "اپ گریڈ",
        "Data Report": "ڈیٹا رپورٹ", "Download Data Report": "ڈیٹا رپورٹ ڈاؤن لوڈ کریں", "Download PDF Report": "PDF رپورٹ ڈاؤن لوڈ کریں", "AI Insights Report": "AI انسائٹس رپورٹ", "Budget Doctor": "بجٹ ڈاکٹر", "Ask Your Money AI": "اپنے منی AI سے پوچھیں", "Bill Reminder Center": "بل ریمائنڈر سینٹر", "Add Bill": "بل شامل کریں", "Bill Name": "بل کا نام", "Due Date": "آخری تاریخ", "Bill Amount": "بل کی رقم", "Already Paid?": "کیا ادا ہو چکا؟", "Bill added.": "بل شامل ہوگیا۔", "Paid": "ادا شدہ",
    },
    "Russian": {
        "Global Control": "Глобальное управление", "Language": "Язык", "Display Currency": "Валюта отображения", "Base Currency": "Базовая валюта", "Choose Section": "Выберите раздел", "AI Tools": "AI-инструменты", "Reports": "Отчеты", "Settings": "Настройки",
        "Premium": "Премиум", "Free Plan": "Бесплатный план", "Plan": "План", "Upgrade to Premium": "Перейти на Премиум", "Account Access": "Доступ к аккаунту", "Sign In": "Войти", "Create Account": "Создать аккаунт", "Forgot Password?": "Забыли пароль?", "Show password": "Показать пароль", "Show or hide password": "Показать или скрыть пароль",
        "Email": "Эл. почта", "Password": "Пароль", "Enter your password": "Введите пароль", "Create a password": "Создайте пароль", "Signed in as": "Выполнен вход как", "Save Budget": "Сохранить бюджет", "Load Budget": "Загрузить бюджет", "Sign Out": "Выйти", "Signed out.": "Вы вышли.", "Signed in successfully.": "Вход выполнен успешно.",
        "Invalid email or password.": "Неверная эл. почта или пароль.", "Enter a valid email address.": "Введите корректный адрес эл. почты.", "Password must be at least 6 characters.": "Пароль должен содержать минимум 6 символов.", "This account already exists.": "Этот аккаунт уже существует.", "Account created and budget saved.": "Аккаунт создан, бюджет сохранен.", "Please sign in first.": "Сначала войдите.",
        "Password reset is not connected yet. For now, create a new account or contact support.": "Сброс пароля пока не подключен. Пока создайте новый аккаунт или обратитесь в поддержку.",
        "Budget Overview": "Обзор бюджета", "Financial Overview": "Финансовый обзор", "Total Budget": "Общий бюджет", "Total Spent": "Всего потрачено", "Remaining": "Осталось", "Income Snapshot": "Сводка дохода", "Income Left": "Остаток дохода", "Savings Rate": "Норма сбережений", "Financial Health Score": "Оценка финансового здоровья", "Category Summary": "Сводка по категориям", "Smart Alerts Center": "Центр умных уведомлений",
        "Set Monthly Budget": "Установить месячный бюджет", "Quick Start Budget Templates": "Быстрые шаблоны бюджета", "Load Basic Monthly Categories": "Загрузить базовые месячные категории", "Default budget categories loaded.": "Категории бюджета по умолчанию загружены.", "Edit Budget Categories": "Редактировать категории бюджета", "Category": "Категория", "Planned Amount": "Плановая сумма", "Add Budget": "Добавить бюджет", "Budget added.": "Бюджет добавлен.",
        "Track Expenses": "Отслеживать расходы", "Date": "Дата", "Description": "Описание", "Amount": "Сумма", "Add Expense": "Добавить расход", "Expense added.": "Расход добавлен.", "Monthly Income": "Месячный доход", "Enter your monthly income": "Введите месячный доход", "Save Income": "Сохранить доход", "Monthly income saved.": "Месячный доход сохранен.", "Current saved income": "Текущий сохраненный доход",
        "Savings Goal": "Цель сбережений", "Save Goal": "Сохранить цель", "Savings goal saved.": "Цель сбережений сохранена.", "Can I Afford This?": "Могу ли я себе это позволить?", "Decision": "Решение", "Summary": "Сводка", "Quick Actions": "Быстрые действия", "AI Command Center": "AI-командный центр", "Next best move": "Следующий лучший шаг", "Dashboard": "Панель", "Budget": "Бюджет", "Expenses": "Расходы", "Income": "Доход", "Bills": "Счета", "Coach": "Коуч", "Report": "Отчет", "Upgrade": "Апгрейд",
        "Data Report": "Отчет данных", "Download Data Report": "Скачать отчет данных", "Download PDF Report": "Скачать PDF-отчет", "AI Insights Report": "Отчет AI-инсайтов", "Budget Doctor": "Доктор бюджета", "Ask Your Money AI": "Спросить финансовый AI", "Bill Reminder Center": "Центр напоминаний о счетах", "Add Bill": "Добавить счет", "Bill Name": "Название счета", "Due Date": "Срок оплаты", "Bill Amount": "Сумма счета", "Already Paid?": "Уже оплачено?", "Bill added.": "Счет добавлен.", "Paid": "Оплачено",
    },
}

for _language_name, _language_pack in ADDITIONAL_LANGUAGE_PACKS.items():
    TRANSLATIONS.setdefault(_language_name, {}).update(_language_pack)


# Expanded Haitian Creole coverage for the elite UI/account/main dashboard layer.
TRANSLATIONS.setdefault("Haitian Creole", {}).update({
    "Account Access": "Aksè kont",
    "Sign In": "Konekte",
    "Create Account": "Kreye kont",
    "Forgot Password?": "Ou bliye modpas la?",
    "Show password": "Montre modpas la",
    "Show or hide password": "Montre oswa kache modpas la",
    "Upgrade to Premium": "Pase nan Premium",
    "Plan": "Plan",
    "Free Plan": "Plan gratis",
    "Premium": "Premium",
    "Email": "Imèl",
    "Password": "Modpas",
    "Enter your password": "Antre modpas ou",
    "Create a password": "Kreye yon modpas",
    "Signed in as": "Konekte kòm",
    "Save Budget": "Sove bidjè",
    "Load Budget": "Chaje bidjè",
    "Sign Out": "Dekonekte",
    "Signed out.": "Ou dekonekte.",
    "Signed in successfully.": "Ou konekte avèk siksè.",
    "Invalid email or password.": "Imèl oswa modpas la pa kòrèk.",
    "Enter a valid email address.": "Antre yon adrès imèl ki valab.",
    "Password must be at least 6 characters.": "Modpas la dwe gen omwen 6 karaktè.",
    "This account already exists.": "Kont sa a deja egziste.",
    "Account created and budget saved.": "Kont lan kreye epi bidjè a sove.",
    "Please sign in first.": "Tanpri konekte anvan.",
    "Password reset is not connected yet. For now, create a new account or contact support.": "Reyinisyalizasyon modpas la poko konekte. Pou kounye a, kreye yon nouvo kont oswa kontakte sipò.",
    "Password reset is not connected yet. For now, create a new account or contact support to reset your password.": "Reyinisyalizasyon modpas la poko konekte. Pou kounye a, kreye yon nouvo kont oswa kontakte sipò pou reyinisyalize modpas ou.",
    "Quick Actions": "Aksyon rapid",
    "Jump straight into the tools people use most.": "Ale dirèkteman nan zouti moun itilize plis yo.",
    "Dashboard": "Tablo kontwòl",
    "Budget": "Bidjè",
    "Expenses": "Depans",
    "Income": "Revni",
    "Bills": "Fakti",
    "Coach": "Antrenè",
    "Report": "Rapò",
    "Upgrade": "Amelyore",
    "AI Command Center": "Sant kòmand IA",
    "Next best move": "Pi bon pwochen aksyon",
    "Budget Burn": "Itilizasyon bidjè",
    "Income Left": "Revni ki rete",
    "Top Spend": "Pi gwo depans",
    "Runway": "Marge ki rete",
    "Healthy": "An sante",
    "Tight": "Sere",
    "Over budget": "Bidjè depase",
    "Savings risk": "Risk pou ekonomi",
    "Financial Overview": "Apèsi finansye",
    "Total Budget": "Bidjè total",
    "Total Spent": "Total depanse",
    "Remaining": "Rès",
    "Income Snapshot": "Apèsi sou revni",
    "Savings Rate": "Pousantaj ekonomi",
    "Financial Health Score": "Nòt sante finansye",
    "Category Summary": "Rezime pa kategori",
    "Smart Alerts Center": "Sant alèt entelijan",
    "Download Data Report": "Telechaje rapò done",
    "Download PDF Report": "Telechaje rapò PDF",
    "AI Insights Report": "Rapò analiz IA",
    "Budget Doctor": "Doktè bidjè",
    "Ask Your Money AI": "Mande IA lajan ou",
    "Bill Reminder Center": "Sant rapèl fakti",
    "Add Bill": "Ajoute fakti",
    "Bill Name": "Non fakti",
    "Due Date": "Dat limit",
    "Bill Amount": "Montan fakti",
    "Already Paid?": "Deja peye?",
    "Bill added.": "Fakti ajoute.",
    "Paid": "Peye",
    "Start your money command center": "Kòmanse sant kòmand lajan ou",
    "No budget yet. Use the quick actions below to build your first monthly plan.": "Pa gen bidjè ankò. Sèvi ak aksyon rapid anba yo pou konstwi premye plan mansyèl ou.",
    "Step 1: Build your budget": "Etap 1: Kreye bidjè ou",
    "Step 2: Track expenses": "Etap 2: Swiv depans yo",
    "Step 3: Get guidance": "Etap 3: Jwenn konsèy",
    "Load starter categories": "Chaje kategori pou kòmanse",
    "Go to income": "Ale nan revni",
    "Open upgrade": "Louvri amelyorasyon",
    "No major budget risks detected. Your spending looks controlled.": "Pa gen gwo risk bidjè detekte. Depans ou yo sanble anba kontwòl.",
    "Create your first budget categories to unlock the dashboard.": "Kreye premye kategori bidjè ou pou debloke tablo kontwòl la.",
    "Not enough data yet": "Pa gen ase done ankò",
    "Pause flexible spending and fix the category that crossed its limit first.": "Mete depans fleksib yo an poz epi korije kategori ki depase limit li an premye.",
    "Protect the remaining budget by slowing down non-essential spending.": "Pwoteje bidjè ki rete a lè ou diminye depans ki pa esansyèl yo.",
    "Your savings goal needs protection. Cut one flexible category this week.": "Objektif ekonomi ou bezwen pwoteksyon. Diminye yon kategori fleksib semèn sa a.",
    "Keep tracking. Your plan has breathing room right now.": "Kontinye swiv. Plan ou a gen yon ti espas toujou.",
    "Add your budget categories first.": "Ajoute kategori bidjè ou yo an premye.",
})


# Stripe + premium checkout translation keys.
for _lang, _items in {
    "French": {
        "Payment was cancelled. You can try again anytime.": "Le paiement a été annulé. Vous pouvez réessayer à tout moment.",
        "🎉 Payment successful! Premium unlocked.": "🎉 Paiement réussi ! Premium est débloqué.",
        "✅ You are already Premium.": "✅ Vous êtes déjà Premium.",
        "Premium money command center": "Centre de contrôle financier Premium",
        "Unlock smarter forecasts, advanced AI guidance, deeper reports, and a more powerful planning workflow.": "Débloquez des prévisions plus intelligentes, des conseils IA avancés, des rapports plus détaillés et un flux de planification plus puissant.",
        "Choose Your Plan": "Choisissez votre forfait",
        "Monthly Premium": "Premium mensuel",
        "One-Time Access": "Accès unique",
        "Best if you want continuous access to premium planning tools.": "Idéal si vous voulez un accès continu aux outils de planification Premium.",
        "Best if you prefer a simple one-time upgrade.": "Idéal si vous préférez une mise à niveau simple en une seule fois.",
        "🚀 Subscribe Monthly": "🚀 S'abonner mensuellement",
        "💳 Buy One-Time Access": "💳 Acheter l'accès unique",
        "⭐ Upgrade Yearly": "⭐ Passer à l'annuel",
        "One-time Stripe link not connected yet.": "Le lien Stripe d'achat unique n'est pas encore connecté.",
        "Stripe setup notes": "Notes de configuration Stripe",
        "Set your Stripe Payment Link success URL to:": "Définissez l'URL de succès du lien de paiement Stripe sur :",
        "Set your Stripe Payment Link cancel URL to:": "Définissez l'URL d'annulation du lien de paiement Stripe sur :",
        "In Streamlit Cloud, add the Stripe links and APP_BASE_URL in Secrets.": "Dans Streamlit Cloud, ajoutez les liens Stripe et APP_BASE_URL dans Secrets.",
        "Temporary demo unlock for local testing only. Remove this before public launch if you do not want demo premium access.": "Déblocage démo temporaire uniquement pour les tests locaux. Supprimez-le avant le lancement public si vous ne voulez pas d'accès démo Premium.",
    },
    "Haitian Creole": {
        "Payment was cancelled. You can try again anytime.": "Peman an te anile. Ou ka eseye ankò nenpòt lè.",
        "🎉 Payment successful! Premium unlocked.": "🎉 Peman reyisi! Premium debloke.",
        "✅ You are already Premium.": "✅ Ou deja Premium.",
        "Premium money command center": "Sant kòmand finans Premium",
        "Unlock smarter forecasts, advanced AI guidance, deeper reports, and a more powerful planning workflow.": "Debloke previzyon pi entelijan, konsèy IA avanse, rapò pi pwofon, ak yon fason planifikasyon ki pi pwisan.",
        "Choose Your Plan": "Chwazi plan ou",
        "Monthly Premium": "Premium chak mwa",
        "One-Time Access": "Aksè yon sèl fwa",
        "Best if you want continuous access to premium planning tools.": "Pi bon si ou vle aksè kontinyèl ak zouti planifikasyon Premium yo.",
        "Best if you prefer a simple one-time upgrade.": "Pi bon si ou prefere yon amelyorasyon senp yon sèl fwa.",
        "🚀 Subscribe Monthly": "🚀 Abòne chak mwa",
        "💳 Buy One-Time Access": "💳 Achte aksè yon sèl fwa",
        "⭐ Upgrade Yearly": "⭐ Pase nan anyèl",
        "One-time Stripe link not connected yet.": "Lyen Stripe pou acha yon sèl fwa a poko konekte.",
        "Stripe setup notes": "Nòt konfigirasyon Stripe",
        "Set your Stripe Payment Link success URL to:": "Mete URL siksè Stripe Payment Link la sou:",
        "Set your Stripe Payment Link cancel URL to:": "Mete URL anilasyon Stripe Payment Link la sou:",
        "In Streamlit Cloud, add the Stripe links and APP_BASE_URL in Secrets.": "Nan Streamlit Cloud, ajoute lyen Stripe yo ak APP_BASE_URL nan Secrets.",
        "Temporary demo unlock for local testing only. Remove this before public launch if you do not want demo premium access.": "Deblokaj demo tanporè pou tès lokal sèlman. Retire sa anvan lansman piblik si ou pa vle aksè demo Premium.",
    },
}.items():
    TRANSLATIONS.setdefault(_lang, {}).update(_items)

PAGE_OPTIONS = {
    "📊 Main Dashboard": ["📊 Dashboard"],
    "📝 Planning": ["📝 Budget Planner", "💸 Expense Tracker", "💵 Income", "🎯 Savings Goal", "🧮 Can I Afford This?", "🚨 Bill Reminder Center", "🔁 Subscriptions"],
    "🧠 AI Tools": ["🩺 Budget Doctor", "🤖 AI Budget Generator", "🧠 What Changed?", "🔥 Ask Your Money AI", "🧬 Money Personality", "🎯 Spending Challenge", "🧠 Money Coach"],
    "📄 Reports": ["📄 Data Report", "📅 AI Insights Report", "📤 Money Snapshot", "💾 Backup & Restore"],
    "💰 Wealth Tools": ["📈 Spending Patterns", "📉 Spending Trends", "🏆 Money Rewards", "📊 Net Worth", "💳 Debt Payoff", "🛟 Emergency Fund"],
    "⚙️ Settings": ["⚙️ Settings"],
    "💎 Upgrade": ["💎 Upgrade"],
}


def strip_emoji_prefix(text):
    return re.sub(r"^[^\w\s]+[\s]*", "", str(text).strip(), flags=re.UNICODE)

def t(text):
    language = st.session_state.get("language", "English")

    if language == "English":
        return text

    # 1. Try static translation first
    static_translation = TRANSLATIONS.get(language, {}).get(text)
    if static_translation:
        return static_translation

    # 2. Try emoji-safe fallback
    clean_text = text.strip()
    for prefix in ["🧹 ", "⚙️ ", "💎 ", "📊 ", "💰 ", "💸 ", "📈 ", "📄 "]:
        if clean_text.startswith(prefix):
            base = clean_text.replace(prefix, "", 1)
            translated = TRANSLATIONS.get(language, {}).get(base)
            if translated:
                return prefix + translated

    # 3. AI fallback
    return auto_translate_cached(text, language)


def page_label(page_name):
    return t(page_name)


def inject_css():
    st.markdown(
        """
        <style>
        :root {
            --emerald-950:#022c22;
            --emerald-900:#064e3b;
            --emerald-700:#047857;
            --emerald-500:#10b981;
            --lime-300:#bef264;
            --ink:#0f172a;
            --muted:#64748b;
            --card:#ffffff;
            --line:rgba(15,23,42,.08);
        }
        html, body, [data-testid="stAppViewContainer"] {
            background:
                radial-gradient(circle at top left, rgba(16,185,129,.16), transparent 28rem),
                linear-gradient(180deg, #f8fafc 0%, #eefdf5 42%, #f8fafc 100%);
        }
        .block-container {
            padding-top: .55rem !important;
            padding-bottom: .65rem !important;
            max-width: 1240px !important;
        }
        [data-testid="stSidebar"] {
            background:
                radial-gradient(circle at top, rgba(190,242,100,.18), transparent 16rem),
                linear-gradient(180deg, #021c18 0%, #033329 42%, #022c22 100%);
            border-right: 1px solid rgba(255,255,255,.12);
        }
        [data-testid="stSidebar"] * { color: #f8fafc !important; }
        [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p { color: #e2e8f0 !important; }
        [data-testid="stSidebar"] hr { margin: .65rem 0 !important; border-color: rgba(255,255,255,.14) !important; }
        div[data-baseweb="select"] > div, input, textarea {
            border-radius: 14px !important;
            border-color: rgba(15,23,42,.13) !important;
            box-shadow: 0 6px 16px rgba(15,23,42,.04) !important;
        }
        [data-testid="stSidebar"] input,
        [data-testid="stSidebar"] textarea {
        background: rgba(255,255,255,.96) !important;
        color: #0f172a !important;
        -webkit-text-fill-color: #0f172a !important;
        border: 1px solid rgba(255,255,255,.28) !important;
        caret-color: #0f172a !important;
        }

        [data-testid="stSidebar"] input::placeholder,
        [data-testid="stSidebar"] textarea::placeholder {
        color: #64748b !important;
        -webkit-text-fill-color: #64748b !important;
        opacity: 1 !important;
        }
        [data-testid="stSidebar"] label,
        [data-testid="stSidebar"] [data-testid="stWidgetLabel"] p {
        color: #f8fafc !important;
        }
        .stButton > button, .stDownloadButton > button, .stLinkButton > a {
            border-radius: 999px !important;
            font-weight: 900 !important;
            border: 1px solid rgba(6,95,70,.20) !important;
            box-shadow: 0 10px 22px rgba(15,23,42,.08);
            transition: transform .15s ease, box-shadow .15s ease, border-color .15s ease;
            cursor: pointer !important;
        }
        .stButton > button:hover, .stDownloadButton > button:hover, .stLinkButton > a:hover {
            transform: translateY(-1px);
            box-shadow: 0 14px 30px rgba(15,23,42,.12);
            border-color: rgba(16,185,129,.55) !important;
        }
        .hero-card {
            position: relative;
            overflow: visible;
            padding: 2.45rem 1.7rem 1.65rem 1.7rem;
            min-height: 222px;
            border-radius: 30px;
            background:
                radial-gradient(circle at top right, rgba(190,242,100,.28), transparent 18rem),
                linear-gradient(135deg, #021f18 0%, #064e3b 50%, #16a34a 100%);
            color: white;
            box-shadow: 0 22px 52px rgba(2,44,34,.26);
            margin-bottom: .55rem;
            border: 1px solid rgba(255,255,255,.20);
        }
        .hero-card:after {
            content:"";
            position:absolute;
            right: 1.1rem;
            top: 1.05rem;
            width: 8.5rem;
            height: 8.5rem;
            background: rgba(255,255,255,.10);
            border-radius: 999px;
            filter: blur(1px);
            pointer-events:none;
        }
        .hero-topline { font-size:.74rem; font-weight:900; letter-spacing:.16em; text-transform:uppercase; opacity:.88; margin:.45rem 0 .52rem 0; line-height:1.45; }
        .hero-title { font-size: 2.34rem; font-weight: 950; margin: .42rem 0 .50rem 0; letter-spacing: -.045em; line-height: 1.32; padding-top:.35rem; padding-bottom:.08rem; }
        .hero-subtitle { font-size: .99rem; opacity: .96; margin: 0; max-width: 880px; line-height:1.5; }
        .pill-row { display: flex; gap: .5rem; flex-wrap: wrap; margin-top: .95rem; }
        .pill {
            padding: .38rem .76rem;
            border-radius: 999px;
            background: rgba(255,255,255,.16);
            border: 1px solid rgba(255,255,255,.30);
            font-size: .82rem;
            font-weight: 850;
            backdrop-filter: blur(8px);
        }

        .sidebar-plan-line {
            padding: .72rem .72rem;
            border-radius: 18px;
            background: rgba(255,255,255,.12);
            border: 1px solid rgba(255,255,255,.20);
            margin-bottom: .55rem;
            font-weight: 900;
        }
        .trust-strip {
            display:grid;
            grid-template-columns: repeat(4, minmax(0,1fr));
            gap:.55rem;
            margin: .55rem 0 .6rem 0;
        }
        .trust-chip {
            border:1px solid rgba(15,23,42,.07);
            background: rgba(255,255,255,.78);
            border-radius: 16px;
            padding:.55rem .7rem;
            box-shadow: 0 10px 24px rgba(15,23,42,.045);
            font-size:.82rem;
            font-weight:850;
            color:#0f172a;
        }
        .quick-nav-wrap {
            padding: .65rem .7rem;
            border-radius: 22px;
            border:1px solid rgba(15,23,42,.07);
            background: rgba(255,255,255,.78);
            box-shadow: 0 14px 30px rgba(15,23,42,.055);
            margin: .15rem 0 .75rem 0;
        }
        .quick-nav-title {
            font-size:.78rem;
            font-weight:950;
            color:#065f46;
            text-transform:uppercase;
            letter-spacing:.12em;
            margin-bottom:.25rem;
        }
        .quick-nav-subtitle { font-size:.84rem; color:#64748b; margin-bottom:.35rem; }
        .elite-empty-grid {
            display:grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap:.75rem;
            margin-top:.75rem;
        }
        .elite-empty-card {
            border:1px solid rgba(15,23,42,.08);
            border-radius:22px;
            background:rgba(255,255,255,.86);
            box-shadow:0 14px 30px rgba(15,23,42,.055);
            padding:1rem;
        }
        .elite-empty-title {font-weight:950;color:#0f172a;margin-bottom:.25rem;}
        .elite-empty-text {color:#64748b;font-size:.9rem;line-height:1.45;}
        .green-divider { height: 3px; border-radius: 999px; background: linear-gradient(90deg, transparent, #22c55e, #10b981, transparent); margin: .45rem 0 .55rem 0; }
        .soft-card {
            padding: .95rem;
            border-radius: 22px;
            border: 1px solid rgba(15,23,42,.075);
            background: rgba(255,255,255,.82);
            box-shadow: 0 14px 30px rgba(15,23,42,.055);
            margin-bottom: .75rem;
        }
        .section-badge { display:inline-block; padding:.24rem .68rem; border-radius:999px; background:#dcfce7; color:#14532d !important; font-weight:950; font-size:.76rem; margin-bottom:.45rem; }
        .command-card {
            padding: .95rem;
            border-radius: 24px;
            border: 1px solid rgba(15,23,42,.08);
            background: linear-gradient(180deg, rgba(255,255,255,.92), rgba(240,253,244,.78));
            box-shadow: 0 18px 36px rgba(15,23,42,.065);
            margin-bottom: .85rem;
        }
        .command-title { font-size:1.05rem; font-weight:950; color:#0f172a; margin-bottom:.25rem; }
        .command-text { font-size:.9rem; color:#475569; margin-bottom:0; line-height:1.45; }
        [data-testid="stMetric"] {
            background: rgba(255,255,255,.88);
            border: 1px solid rgba(15,23,42,.075);
            border-radius: 20px;
            padding: 13px 15px;
            box-shadow: 0 12px 26px rgba(15,23,42,.055);
        }
        [data-testid="stMetricLabel"] p { color:#64748b !important; font-weight:900 !important; }
        [data-testid="stMetricValue"] { color:#0f172a !important; font-weight:950 !important; }
        .footer { text-align:center; padding:.55rem 0 0 0; color:#64748b; font-size:.84rem; }
        .plan-row-card {
            padding:.55rem .65rem;
            border-radius:18px;
            background:rgba(255,255,255,.10);
            border:1px solid rgba(255,255,255,.16);
            margin:.25rem 0 .15rem 0;
        }
        .mini-help-text {
            font-size:.78rem;
            line-height:1.35;
            opacity:.88;
            margin-top:.25rem;
        }
        .account-mini-label {
            font-size:.76rem;
            font-weight:900;
            letter-spacing:.08em;
            text-transform:uppercase;
            opacity:.88;
            margin:.15rem 0 .25rem 0;
        }
        [data-testid="stSidebar"] .stButton > button {
            min-height: 2.35rem;
            background: linear-gradient(135deg, rgba(236,253,245,.98), rgba(187,247,208,.95)) !important;
            color:#022c22 !important;
            border:1px solid rgba(190,242,100,.42) !important;
        }
        [data-testid="stSidebar"] .stButton > button p {
            color:#022c22 !important;
            font-weight:950 !important;
        }
        [data-testid="stSidebar"] [data-testid="stAlert"] * {
            color:#0f172a !important;
        }

        @media (max-width: 768px) {
            .block-container { padding-left:.85rem !important; padding-right:.85rem !important; }
            .hero-title { font-size:1.42rem !important; }
            .hero-subtitle { font-size:.88rem !important; }
    
        .sidebar-plan-line {
            padding: .72rem .72rem;
            border-radius: 18px;
            background: rgba(255,255,255,.12);
            border: 1px solid rgba(255,255,255,.20);
            margin-bottom: .55rem;
            font-weight: 900;
        }
        .trust-strip { grid-template-columns:1fr; }
            .elite-empty-grid { grid-template-columns:1fr; }
            h1 { font-size:1.55rem !important; }
            h2, h3 { font-size:1.12rem !important; }
        }
        
        /* Fix unreadable Streamlit alert boxes in sidebar */
[data-testid="stSidebar"] [data-testid="stAlert"] *,
[data-testid="stSidebar"] [data-testid="stAlert"] p,
[data-testid="stSidebar"] [data-testid="stAlert"] div {
    color: #0f172a !important;
    -webkit-text-fill-color: #0f172a !important;
}

[data-testid="stSidebar"] [data-testid="stAlert"] {
    background: #fff1f2 !important;
    border: 1px solid #fb7185 !important;
    border-radius: 12px !important;
}

/* Make Streamlit error/warning boxes readable in sidebar */
[data-testid="stSidebar"] [data-testid="stAlert"],
[data-testid="stSidebar"] [role="alert"] {
    background: #fff1f2 !important;
    border: 1px solid #fb7185 !important;
    border-radius: 12px !important;
}

[data-testid="stSidebar"] [data-testid="stAlert"] *,
[data-testid="stSidebar"] [role="alert"] *,
[data-testid="stSidebar"] .stAlert *,
[data-testid="stSidebar"] div[data-baseweb="notification"] * {
    color: #111827 !important;
    -webkit-text-fill-color: #111827 !important;
}
        
        

        /* =========================
           V2 ELITE SAAS UPGRADE
           Premium product polish layer
           ========================= */
        .v2-hero-shell {
            position: relative;
            overflow: hidden;
            border-radius: 34px;
            padding: 1.35rem 1.45rem;
            margin: .15rem 0 .9rem 0;
            background:
                radial-gradient(circle at 8% 0%, rgba(190,242,100,.35), transparent 21rem),
                radial-gradient(circle at 94% 12%, rgba(52,211,153,.28), transparent 22rem),
                linear-gradient(135deg, #011713 0%, #033a2f 44%, #0f766e 100%);
            border: 1px solid rgba(255,255,255,.18);
            box-shadow: 0 28px 70px rgba(2,44,34,.30);
            color: #ffffff;
        }
        .v2-hero-shell:before {
            content: "";
            position: absolute;
            inset: 0;
            background-image:
                linear-gradient(rgba(255,255,255,.06) 1px, transparent 1px),
                linear-gradient(90deg, rgba(255,255,255,.06) 1px, transparent 1px);
            background-size: 38px 38px;
            mask-image: linear-gradient(90deg, rgba(0,0,0,.7), transparent);
            pointer-events: none;
        }
        .v2-hero-inner { position: relative; z-index: 2; }
        .v2-kicker {
            display: inline-flex;
            align-items: center;
            gap: .45rem;
            padding: .34rem .74rem;
            border-radius: 999px;
            background: rgba(255,255,255,.14);
            border: 1px solid rgba(255,255,255,.25);
            font-size: .76rem;
            font-weight: 950;
            letter-spacing: .11em;
            text-transform: uppercase;
        }
        .v2-hero-title {
            font-size: clamp(2.1rem, 4vw, 4.15rem);
            line-height: 1.02;
            letter-spacing: -.06em;
            font-weight: 1000;
            margin: .82rem 0 .58rem 0;
        }
        .v2-hero-copy {
            color: rgba(255,255,255,.88);
            font-size: 1.04rem;
            line-height: 1.62;
            max-width: 840px;
            margin: 0 0 1.05rem 0;
        }
        .v2-chip-row { display:flex; gap:.55rem; flex-wrap:wrap; }
        .v2-chip {
            padding: .45rem .78rem;
            border-radius: 999px;
            background: rgba(255,255,255,.12);
            border: 1px solid rgba(255,255,255,.22);
            color: #f8fafc;
            font-weight: 900;
            font-size: .82rem;
        }
        .v2-plan-card {
            position: relative;
            min-height: 420px;
            border-radius: 28px;
            padding: 1.2rem;
            background:
                linear-gradient(180deg, rgba(255,255,255,.98), rgba(248,250,252,.94));
            border: 1px solid rgba(15,23,42,.08);
            box-shadow: 0 24px 55px rgba(15,23,42,.10);
            overflow: hidden;
        }
        .v2-plan-card.featured {
            border: 1px solid rgba(16,185,129,.36);
            box-shadow: 0 28px 70px rgba(6,95,70,.18);
        }
        .v2-plan-card.featured:before {
            content: "Best value";
            position: absolute;
            top: 1rem;
            right: 1rem;
            padding: .35rem .72rem;
            border-radius: 999px;
            background: #022c22;
            color: #bef264;
            font-size: .72rem;
            font-weight: 950;
            letter-spacing: .06em;
            text-transform: uppercase;
        }
        .v2-plan-name { color:#0f172a; font-size:1.2rem; font-weight:1000; margin-bottom:.35rem; }
        .v2-plan-price { color:#022c22; font-size:2.55rem; font-weight:1000; letter-spacing:-.05em; margin:.25rem 0; }
        .v2-plan-note { color:#64748b; font-weight:750; font-size:.9rem; margin-bottom:.95rem; }
        .v2-feature-list { margin:.7rem 0 1rem 0; padding:0; list-style:none; }
        .v2-feature-list li {
            padding:.45rem 0;
            color:#334155;
            font-weight:760;
            border-bottom:1px solid rgba(15,23,42,.055);
        }
        .v2-feature-list li:before { content:"✓"; color:#059669; font-weight:1000; margin-right:.5rem; }
        .v2-mini-grid {
            display:grid;
            grid-template-columns: repeat(4, minmax(0,1fr));
            gap:.65rem;
            margin:.85rem 0 1rem 0;
        }
        .v2-mini-tile {
            padding:.82rem;
            border-radius:20px;
            background:rgba(255,255,255,.86);
            border:1px solid rgba(15,23,42,.07);
            box-shadow:0 14px 34px rgba(15,23,42,.055);
        }
        .v2-mini-title {font-weight:1000;color:#0f172a;font-size:.88rem;margin-bottom:.2rem;}
        .v2-mini-text {color:#64748b;font-size:.8rem;line-height:1.35;}
        .v2-billing-note {
            border-radius: 20px;
            padding: .9rem 1rem;
            background: #ecfeff;
            border: 1px solid rgba(6,182,212,.25);
            color: #155e75;
            font-weight: 820;
            margin-top: .9rem;
        }
        @media (max-width: 900px) {
            .v2-mini-grid { grid-template-columns: repeat(2, minmax(0,1fr)); }
            .trust-strip { grid-template-columns: repeat(2, minmax(0,1fr)); }
        }
</style>
        """,
        unsafe_allow_html=True,
    )

def render_hero():
    hero_title = t("💰 ExplainMyBudget AI")
    hero_subtitle = t("Your money, clearly explained — budget smarter, spend wiser, and build financial confidence anywhere in the world.")
    pill_global = t("🌍 Global currency")
    pill_ai = t("🤖 AI-style insights")
    pill_reports = t("📊 Reports")
    pill_rewards = t("🏆 Rewards")
    pill_mobile = t("📱 Mobile-ready")
    plan_text = t("Premium") if is_premium_user() else t("Free Plan")
    st.markdown(
        f"""
        <div class="hero-card">
            <div class="hero-topline">Personal finance command center · {plan_text}</div>
            <div class="hero-title">{hero_title}</div>
            <p class="hero-subtitle">{hero_subtitle}</p>
            <div class="pill-row">
                <span class="pill">{pill_global}</span>
                <span class="pill">{pill_ai}</span>
                <span class="pill">{pill_reports}</span>
                <span class="pill">{pill_rewards}</span>
                <span class="pill">{pill_mobile}</span>
            </div>
        </div>
        <div class="trust-strip">
            <div class="trust-chip">🛡️ Private local saves</div>
            <div class="trust-chip">⚡ Fast budget checks</div>
            <div class="trust-chip">🔮 Forecast-ready</div>
            <div class="trust-chip">🌍 Multi-currency</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

def section_card(label, body):
    st.markdown(f"<div class='soft-card'><div class='section-badge'>{label}</div><div>{body}</div></div>", unsafe_allow_html=True)


def render_command_center(summary_df, total_planned, total_spent, total_remaining, monthly_income):
    savings_goal = float(st.session_state.get("savings_goal", 0.0) or 0.0)
    burn_rate = (total_spent / total_planned * 100) if total_planned > 0 else 0
    income_left = monthly_income - total_spent if monthly_income > 0 else 0
    if total_planned == 0:
        next_move = t("Create your first budget categories to unlock the dashboard.")
        runway = t("Not enough data yet")
    elif total_spent > total_planned:
        next_move = t("Pause flexible spending and fix the category that crossed its limit first.")
        runway = t("Over budget")
    elif burn_rate >= 80:
        next_move = t("Protect the remaining budget by slowing down non-essential spending.")
        runway = t("Tight")
    elif savings_goal > 0 and monthly_income > 0 and income_left < savings_goal:
        next_move = t("Your savings goal needs protection. Cut one flexible category this week.")
        runway = t("Savings risk")
    else:
        next_move = t("Keep tracking. Your plan has breathing room right now.")
        runway = t("Healthy")

    top_category = t("None yet")
    if summary_df is not None and not summary_df.empty and "Spent" in summary_df.columns:
        ranked = summary_df.sort_values("Spent", ascending=False)
        if not ranked.empty and float(ranked.iloc[0].get("Spent", 0) or 0) > 0:
            top_category = str(ranked.iloc[0].get("Category", t("None yet")))

    st.markdown(
        f"""
        <div class="command-card">
            <div class="command-title">🧠 {t("AI Command Center")}</div>
            <p class="command-text"><b>{t("Next best move")}:</b> {next_move}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(t("Budget Burn"), f"{burn_rate:.1f}%")
    c2.metric(t("Income Left"), money(income_left))
    c3.metric(t("Top Spend"), top_category)
    c4.metric(t("Runway"), runway)



def render_quick_navigation(current_page):
    st.markdown(
        f"""
        <div class="quick-nav-wrap">
            <div class="quick-nav-title">{t("Quick Actions")}</div>
            <div class="quick-nav-subtitle">{t("Jump straight into the tools people use most.")}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    quick_items = [
        ("📊 Dashboard", "📊 Dashboard"),
        ("📝 Budget", "📝 Budget Planner"),
        ("💸 Expenses", "💸 Expense Tracker"),
        ("💵 Income", "💵 Income"),
        ("🚨 Bills", "🚨 Bill Reminder Center"),
        ("🧠 Coach", "🧠 Money Coach"),
        ("📄 Report", "📄 Data Report"),
        ("💎 Upgrade", "💎 Upgrade"),
    ]
    cols = st.columns(8)
    selected = current_page
    for col, (label, target) in zip(cols, quick_items):
        with col:
            button_label = t(label)
            if target == current_page:
                button_label = "✓ " + button_label
            if st.button(button_label, key=f"quick_nav_{target}", use_container_width=True):
                selected = target
                st.session_state["active_page"] = target
    return selected


def render_empty_dashboard():
    st.markdown("### " + t("Start your money command center"))
    st.info(t("No budget yet. Use the quick actions below to build your first monthly plan."))
    st.markdown(
        f"""
        <div class="elite-empty-grid">
            <div class="elite-empty-card">
                <div class="elite-empty-title">📝 {t("Step 1: Build your budget")}</div>
                <div class="elite-empty-text">{t("Add categories like housing, food, transport, bills, savings, and debt.")}</div>
            </div>
            <div class="elite-empty-card">
                <div class="elite-empty-title">💸 {t("Step 2: Track expenses")}</div>
                <div class="elite-empty-text">{t("Log spending so the dashboard can show alerts, trends, and remaining money.")}</div>
            </div>
            <div class="elite-empty-card">
                <div class="elite-empty-title">🧠 {t("Step 3: Get guidance")}</div>
                <div class="elite-empty-text">{t("Use AI-style recommendations to understand what changed and what to do next.")}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button(t("Load starter categories"), use_container_width=True, key="empty_load_starter"):
            st.session_state["budget_df"] = pd.DataFrame(
                [["Housing", 0.0], ["Food", 0.0], ["Transportation", 0.0], ["Utilities", 0.0],
                 ["Debt Payments", 0.0], ["Savings", 0.0], ["Health", 0.0], ["Entertainment", 0.0],
                 ["Shopping", 0.0], ["Family Support", 0.0], ["Education", 0.0], ["Other", 0.0]],
                columns=["Category", "Planned"],
            )
            st.success(t("Default budget categories loaded."))
    with c2:
        if st.button(t("Go to income"), use_container_width=True, key="empty_go_income"):
            st.session_state["active_page"] = "💵 Income"
            st.rerun()
    with c3:
        if st.button(t("Open upgrade"), use_container_width=True, key="empty_go_upgrade"):
            st.session_state["active_page"] = "💎 Upgrade"
            st.rerun()

def render_footer():
    st.markdown("<div class='green-divider'></div>", unsafe_allow_html=True)
    st.markdown("<div class='footer'>Clean money. Clear choices. Better decisions. © 2026 ExplainMyBudget AI</div>", unsafe_allow_html=True)

def inject_language_direction_css():
    """Improve readability for right-to-left languages such as Arabic and Urdu."""
    if st.session_state.get("language") in ["Standard Arabic", "Urdu"]:
        st.markdown(
            """
            <style>
            .stMarkdown, [data-testid="stMarkdownContainer"], p, h1, h2, h3, h4, h5, h6, label {
                direction: rtl;
                text-align: right;
            }
            .stButton > button, .stDownloadButton > button {
                direction: rtl;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )


def init_state():
    defaults = {
        "debts_df": pd.DataFrame(columns=["Name", "Balance", "Rate"]),
        "subscriptions_df": pd.DataFrame(columns=["Name", "Cost"]),
        "goals_df": pd.DataFrame(columns=["Goal", "Target", "Saved"]),
        "budget_df": pd.DataFrame(columns=["Category", "Planned"]),
        "expense_df": pd.DataFrame(columns=["Date", "Category", "Description", "Amount"]),
        "bills_df": pd.DataFrame(columns=["Bill Name", "Due Date", "Amount", "Paid"]),
        "assets_df": pd.DataFrame(columns=["Asset", "Value"]),
        "liabilities_df": pd.DataFrame(columns=["Liability", "Amount"]),
        "savings_goal": 0.0,
        "monthly_income": 0.0,
        "user_plan": FREE_PLAN,
        "premium_trial_used": False,
        "premium_trial_active": False,
        "base_currency": "USD",
        "currency": "USD",
        "language": "English",
        "account_email": "",
        "account_logged_in": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value
        
def is_premium_user():
    return (
        st.session_state.get("user_plan", FREE_PLAN) == PREMIUM_PLAN
        or st.session_state.get("premium_trial_active", False)
    )

def activate_one_free_trial():
    if st.session_state.get("premium_trial_used", False):
        return False

    st.session_state["premium_trial_used"] = True
    st.session_state["premium_trial_active"] = True
    return True

def require_premium(feature_name="this feature"):
    if not is_premium_user():

        # Message
        st.warning(t(f"🔒 {feature_name} is a Premium feature."))
        st.info(t("Go to 💎 Upgrade to unlock this feature."))

        # Upgrade button
        if st.button("💎 Upgrade to Premium", key=f"upgrade_{feature_name}"):
            st.session_state["page"] = "💎 Upgrade"
            st.rerun()

        st.stop()

# ============================================================
# STRIPE PRICE ID CHECKOUT HELPERS
# Uses two Stripe Price IDs:
#   STRIPE_PRICE_MONTHLY   -> recurring monthly subscription price
#   STRIPE_PRICE_ONE_TIME  -> one-time/lifetime access price
# ============================================================

def get_secret_value(name, default=""):
    """Read secrets from environment variables first, then Streamlit secrets."""
    value = os.getenv(name, default)
    if value:
        return value
    try:
        return st.secrets.get(name, default)
    except Exception:
        return default


def get_app_base_url():
    base_url = get_secret_value("APP_BASE_URL", "http://localhost:8501")
    return str(base_url).rstrip("/")


def get_stripe_price_ids():
    """Return the two Stripe Price IDs used by this app."""
    monthly = get_secret_value("STRIPE_PRICE_MONTHLY")
    one_time = get_secret_value("STRIPE_PRICE_ONE_TIME")
    return {
        "monthly": monthly,
        "one_time": one_time,
    }


def get_current_account_email():
    return (
        st.session_state.get("account_email")
        or st.session_state.get("user_email")
        or ""
    ).lower().strip()


def ensure_stripe_ready():
    if stripe is None:
        st.error("Stripe package is not installed. Run: pip install stripe")
        return False

    secret_key = get_secret_value("STRIPE_SECRET_KEY")
    if not secret_key:
        st.error("STRIPE_SECRET_KEY is missing from your .env or Streamlit Secrets.")
        return False

    stripe.api_key = secret_key
    return True


def save_premium_status(email, plan_source="stripe"):
    """Save premium status locally and in Supabase when available."""
    email = (email or "").lower().strip()
    if not email:
        return False

    st.session_state["user_plan"] = PREMIUM_PLAN
    st.session_state["account_email"] = email
    st.session_state["account_logged_in"] = True

    users = load_users()
    users.setdefault(email, {})
    users[email]["is_premium"] = True
    users[email]["plan"] = PREMIUM_PLAN
    users[email]["plan_source"] = plan_source
    save_users(users)

    supabase = get_supabase_client()
    if supabase is not None:
        try:
            existing = (
                supabase.table("user_profiles")
                .select("email")
                .eq("email", email)
                .eq("app", APP_NAME)
                .execute()
            )

            payload = {
                "email": email,
                "app": APP_NAME,
                "is_premium": True,
            }

            if existing.data:
                supabase.table("user_profiles")                     .update({"is_premium": True})                     .eq("email", email)                     .eq("app", APP_NAME)                     .execute()
            else:
                supabase.table("user_profiles").insert(payload).execute()
        except Exception:
            # Local save still keeps the account premium even if Supabase is unavailable.
            pass

    return True


def mark_current_user_premium(email=None, plan_source="stripe"):
    """Unlock premium permanently for the current signed-in user."""
    email = (email or get_current_account_email()).lower().strip()
    if not email:
        st.session_state["user_plan"] = PREMIUM_PLAN
        return False
    return save_premium_status(email, plan_source=plan_source)


def load_premium_status_for_signed_in_user():
    email = get_current_account_email()

    if not email:
        return

    users = load_users()
    if users.get(email, {}).get("is_premium"):
        st.session_state["user_plan"] = PREMIUM_PLAN
        return

    supabase = get_supabase_client()
    if supabase is None:
        return

    try:
        profile = (
            supabase.table("user_profiles")
            .select("is_premium")
            .eq("email", email)
            .eq("app", APP_NAME)
            .execute()
        )

        if profile.data and profile.data[0].get("is_premium"):
            st.session_state["user_plan"] = PREMIUM_PLAN
        else:
            st.session_state["user_plan"] = FREE_PLAN

    except Exception:
        st.session_state["user_plan"] = FREE_PLAN


def create_checkout_session(price_id=None, checkout_mode=None, plan_name=None):
    """Create a Stripe Checkout Session and return its URL.

    Supports both safe call styles:
    1) create_checkout_session("monthly")
    2) create_checkout_session(price_id=..., checkout_mode=..., plan_name=...)
    """
    prices = get_stripe_price_ids()

    # Friendly shorthand requested for the Upgrade buttons.
    if price_id in ["monthly", "subscription"] and checkout_mode is None:
        plan_name = "monthly"
        checkout_mode = "subscription"
        price_id = prices.get("monthly")

    elif price_id in ["one_time", "one-time", "payment"] and checkout_mode is None:
        plan_name = "one_time"
        checkout_mode = "payment"
        price_id = prices.get("one_time")

    if not price_id:
        st.error(t("Stripe price ID not connected yet. Check STRIPE_PRICE_MONTHLY or STRIPE_PRICE_ONE_TIME in .env / Streamlit Secrets."))
        return None

    if not checkout_mode:
        checkout_mode = "subscription" if plan_name == "monthly" else "payment"

    if not plan_name:
        plan_name = "monthly" if checkout_mode == "subscription" else "one_time"

    if not ensure_stripe_ready():
        return None

    email = get_current_account_email()
    if not email:
        st.warning(t("Please sign in first."))
        return None

    app_base_url = get_app_base_url()
    success_url = f"{app_base_url}?payment=success&session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{app_base_url}?payment=cancelled"

    try:
        session = stripe.checkout.Session.create(
            mode=checkout_mode,
            line_items=[{"price": price_id, "quantity": 1}],
            customer_email=email,
            client_reference_id=email,
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={
                "email": email,
                "app": APP_NAME,
                "plan": plan_name,
            },
        )
        return session.url
    except Exception as e:
        st.error(f"Stripe checkout error: {e}")
        return None

def redirect_to_checkout(checkout_url):
    """Open Stripe Checkout immediately after the session is created."""
    if not checkout_url:
        return

    components.html(
        f"""
        <script>
            window.parent.location.href = {json.dumps(checkout_url)};
        </script>
        <p>Redirecting to Stripe Checkout...</p>
        """,
        height=80,
    )
    st.link_button("Open Stripe Checkout", checkout_url, use_container_width=True)


def handle_payment_return():
    """Handle Stripe redirect, verify Checkout Session, unlock Premium, then clear URL params."""
    try:
        payment_status = st.query_params.get("payment")
        session_id = st.query_params.get("session_id")
    except Exception:
        payment_status = None
        session_id = None

    if isinstance(payment_status, list):
        payment_status = payment_status[0] if payment_status else None

    if isinstance(session_id, list):
        session_id = session_id[0] if session_id else None

    if payment_status == "success":
        st.session_state["payment_returned_success"] = True
        email = None
        stripe_verified = False

        # Best path: read the Stripe Checkout Session from the returned session_id.
        if session_id and str(session_id).strip().lower() != "test":
            try:
                stripe_key = get_secret_value("STRIPE_SECRET_KEY")
                if stripe_key:
                    stripe.api_key = stripe_key

                checkout_session = stripe.checkout.Session.retrieve(session_id)
                stripe_verified = True

                customer_details = None
                try:
                    customer_details = checkout_session.get("customer_details")
                except Exception:
                    customer_details = getattr(checkout_session, "customer_details", None)

                if customer_details:
                    try:
                        email = customer_details.get("email")
                    except Exception:
                        email = getattr(customer_details, "email", None)

                if not email:
                    try:
                        email = checkout_session.get("customer_email")
                    except Exception:
                        email = getattr(checkout_session, "customer_email", None)

                if not email:
                    try:
                        email = checkout_session.get("client_reference_id")
                    except Exception:
                        email = getattr(checkout_session, "client_reference_id", None)

                if not email:
                    try:
                        metadata = checkout_session.get("metadata")
                    except Exception:
                        metadata = getattr(checkout_session, "metadata", None)
                    if metadata:
                        try:
                            email = metadata.get("email")
                        except Exception:
                            email = getattr(metadata, "email", None)

            except Exception as e:
                st.warning(f"Payment returned, but Stripe session could not be verified: {e}")
# =========================
# PAYMENT SUCCESS HANDLER
# =========================

params = st.query_params

if params.get("payment") == "success":

    email = st.session_state.get("user_email")

    if email:
        supabase.table("user_profiles").update({
            "is_premium": True,
            "plan_source": "stripe_manual"
        }).eq("email", email).execute()

        st.success("🎉 Premium activated!")

        # Optional: prevent repeating on refresh
        st.query_params.clear()

        # Fallback for local testing or if Stripe session lookup failed.
        if not email:
            email = get_current_account_email()

        if email:
            email = email.lower().strip()
            try:
                mark_current_user_premium(email, plan_source="stripe")
                st.session_state["user_email"] = email
                st.session_state["account_email"] = email
                st.session_state["account_logged_in"] = True
                st.session_state["user_plan"] = PREMIUM_PLAN
                sync_premium_from_supabase(email)

                if stripe_verified:
                    st.success(t("🎉 Payment successful! Premium unlocked."))
                else:
                    st.success(t("🎉 Payment successful! Premium unlocked for this signed-in account."))
            except Exception as e:
                st.error(f"Payment succeeded, but Premium could not be saved: {e}")
        else:
            st.success(t("🎉 Payment successful! Please sign in to refresh Premium access."))

        try:
            st.query_params.clear()
        except Exception:
            pass

    elif payment_status == "cancelled":
        st.warning(t("Payment was cancelled. You can try again anytime."))
        try:
            st.query_params.clear()
        except Exception:
            pass

def render_stripe_upgrade_page():
    """V2 elite pricing and billing screen."""
    st.markdown(
        f"""
        <div class="v2-hero-shell">
            <div class="v2-hero-inner">
                <div class="v2-kicker">💎 {t("Premium money command center")}</div>
                <div class="v2-hero-title">{t("Upgrade Your Experience")}</div>
                <p class="v2-hero-copy">
                    {t("Unlock smarter forecasts, advanced AI guidance, deeper reports, and a more powerful planning workflow.")}
                </p>
                <div class="v2-chip-row">
                    <span class="v2-chip">🧠 {t("AI Money Coach")}</span>
                    <span class="v2-chip">🔮 {t("Forecasting Engine")}</span>
                    <span class="v2-chip">📄 {t("Advanced Reports")}</span>
                    <span class="v2-chip">🚨 {t("Smart Alerts Center")}</span>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if is_premium_user():
        st.success(t("✅ You are already Premium."))
    else:
        st.info(t("Free Plan"))
    st.markdown("""
<style>

</style>
""", unsafe_allow_html=True)

    st.markdown(
        f"""
        <div class="v2-mini-grid">
            <div class="v2-mini-tile"><div class="v2-mini-title">🧠 {t("AI Insights Report")}</div><div class="v2-mini-text">{t("Generate smarter money explanations and next steps.")}</div></div>
            <div class="v2-mini-tile"><div class="v2-mini-title">🔮 {t("Forecasting Engine")}</div><div class="v2-mini-text">{t("See possible overspending before it happens.")}</div></div>
            <div class="v2-mini-tile"><div class="v2-mini-title">📄 {t("Data Report")}</div><div class="v2-mini-text">{t("Export cleaner reports for review and planning.")}</div></div>
            <div class="v2-mini-tile"><div class="v2-mini-title">🌍 {t("Global money context")}</div><div class="v2-mini-text">{t("Plan across currencies with clearer context.")}</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    prices = get_stripe_price_ids()

    st.markdown("### " + t("Choose Your Plan"))
    col1, col2 = st.columns(2)

    with col1:
        st.markdown(
            f"""
            <div class="v2-plan-card featured">
                <div class="v2-plan-name">🔄 {t("Monthly Premium")}</div>
                <div class="v2-plan-price">$14<span style="font-size:1rem;color:#64748b;letter-spacing:0;">/month</span></div>
                <div class="v2-plan-note">{t("Best if you want continuous access to premium planning tools.")}</div>
                <ul class="v2-feature-list">
                    <li>{t("AI Insights & Smart Analysis")}</li>
                    <li>{t("Forecasting & Scenario Planning")}</li>
                    <li>{t("Advanced Reports")}</li>
                    <li>{t("Smart Alerts Center")}</li>
                    <li>{t("Money Coach")}</li>
                </ul>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if prices.get("monthly"):
            if st.button(t("🚀 Subscribe Monthly"), key="stripe_monthly_checkout_v2", use_container_width=True):
                checkout_url = create_checkout_session("monthly")
                redirect_to_checkout(checkout_url)
        else:
            st.info(t("Monthly Stripe price ID not connected yet."))

    with col2:
        st.markdown(
            f"""
            <div class="v2-plan-card">
                <div class="v2-plan-name">💳 {t("One-Time Access")}</div>
                <div class="v2-plan-price">$10.99<span style="font-size:1rem;color:#64748b;letter-spacing:0;"> one-time</span></div>
                <div class="v2-plan-note">{t("Best if you prefer a simple one-time upgrade.")}</div>
                <ul class="v2-feature-list">
                    <li>{t("Full access")}</li>
                    <li>{t("No subscription")}</li>
                    <li>{t("Premium reports")}</li>
                    <li>{t("Smart savings guidance")}</li>
                    <li>{t("Budget Doctor")}</li>
                </ul>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if prices.get("one_time"):
            if st.button(t("💳 Buy One-Time Access"), key="stripe_one_time_checkout_v2", use_container_width=True):
                checkout_url = create_checkout_session("one_time")
                redirect_to_checkout(checkout_url)
        else:
            st.info(t("One-time Stripe price ID not connected yet."))

    st.info("To cancel or change your plan, contact support.")

    with st.expander(t("Stripe setup notes"), expanded=False):
        app_base_url = get_app_base_url()
        st.write(t("Use these Streamlit Secrets or .env values:"))
        st.code(
            "STRIPE_SECRET_KEY=sk_test_or_live...\n"
            "STRIPE_PRICE_MONTHLY=price_...\n"
            "STRIPE_PRICE_ONE_TIME=price_...\n"
            f"APP_BASE_URL={app_base_url}"
        )
        st.write(t("Set your Stripe Checkout success URL to include the checkout session id."))

def format_money(amount):
    try:
        amount = float(amount)
    except Exception:
        amount = 0.0
    currency = st.session_state.get("currency", "USD")
    symbol = SUPPORTED_CURRENCIES.get(currency, {}).get("symbol", "$")
    return f"{symbol}{amount:,.2f}"


@st.cache_data(ttl=3600)
def get_exchange_rate(from_currency, to_currency):
    if from_currency == to_currency:
        return 1.0
    try:
        url = f"https://api.exchangerate.host/convert?from={from_currency}&to={to_currency}&amount=1"
        response = requests.get(url, timeout=5)
        data = response.json()
        result = data.get("result")
        if result:
            return float(result)
    except Exception:
        pass

    fallback_rates = {
        ("USD", "EUR"): 0.92, ("USD", "GBP"): 0.79, ("USD", "CAD"): 1.36,
        ("USD", "NGN"): 1500.0, ("USD", "INR"): 83.0, ("USD", "BRL"): 5.0,
        ("USD", "HTG"): 132.0, ("USD", "MXN"): 17.0, ("USD", "ZAR"): 18.0, ("USD", "JPY"): 155.0,
    }
    if (from_currency, to_currency) in fallback_rates:
        return fallback_rates[(from_currency, to_currency)]
    if (to_currency, from_currency) in fallback_rates:
        return 1 / fallback_rates[(to_currency, from_currency)]
    return 1.0


def convert_currency(amount, from_currency=None, to_currency=None):
    try:
        amount = float(amount)
    except Exception:
        amount = 0.0
    from_currency = from_currency or st.session_state.get("base_currency", "USD")
    to_currency = to_currency or st.session_state.get("currency", "USD")
    return round(amount * get_exchange_rate(from_currency, to_currency), 2)


def money(amount):
    return format_money(convert_currency(amount))


# ============================================================
# LOCAL USER ACCOUNTS + SAVED BUDGETS
# For production, replace this starter system with Supabase.
# ============================================================

APP_DATA_DIR = Path(__file__).resolve().parent / "app_data"
APP_DATA_DIR.mkdir(exist_ok=True)
USERS_FILE = APP_DATA_DIR / "users.json"
TRANSLATION_MEMORY_FILE = APP_DATA_DIR / "translation_memory.json"


def load_users():
    if USERS_FILE.exists():
        try:
            return json.loads(USERS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}

def save_users(users):
    USERS_FILE.write_text(json.dumps(users, indent=2), encoding="utf-8")

def hash_password(password):
    return hashlib.sha256(str(password).encode("utf-8")).hexdigest()

def safe_user_key(email):
    return re.sub(r"[^a-zA-Z0-9_-]", "_", email.lower().strip())

def get_user_save_file(email=None):
    email = email or st.session_state.get("account_email", "")
    return APP_DATA_DIR / f"budget_{safe_user_key(email)}.json"

def dataframe_to_records(df):
    if df is None or df.empty:
        return []
    safe = df.copy()
    for col in safe.columns:
        safe[col] = safe[col].astype(str)
    return safe.to_dict(orient="records")

def records_to_dataframe(records, columns):
    if not records:
        return pd.DataFrame(columns=columns)
    df = pd.DataFrame(records)
    for col in columns:
        if col not in df.columns:
            df[col] = None
    return df[columns]

def get_current_budget_state():
    return {
        "monthly_income": float(st.session_state.get("monthly_income", 0.0) or 0.0),
        "savings_goal": float(st.session_state.get("savings_goal", 0.0) or 0.0),
        "currency": st.session_state.get("currency", "USD"),
        "base_currency": st.session_state.get("base_currency", "USD"),
        "budget_df": dataframe_to_records(st.session_state.get("budget_df")),
        "expense_df": dataframe_to_records(st.session_state.get("expense_df")),
        "bills_df": dataframe_to_records(st.session_state.get("bills_df")),
        "assets_df": dataframe_to_records(st.session_state.get("assets_df")),
        "liabilities_df": dataframe_to_records(st.session_state.get("liabilities_df")),
    }

def apply_budget_state(data):
    st.session_state["monthly_income"] = float(data.get("monthly_income", 0.0) or 0.0)
    st.session_state["savings_goal"] = float(data.get("savings_goal", 0.0) or 0.0)
    st.session_state["currency"] = data.get("currency", "USD")
    st.session_state["base_currency"] = data.get("base_currency", "USD")
    st.session_state["budget_df"] = records_to_dataframe(data.get("budget_df", []), ["Category", "Planned"])
    st.session_state["expense_df"] = records_to_dataframe(data.get("expense_df", []), ["Date", "Category", "Description", "Amount"])
    st.session_state["bills_df"] = records_to_dataframe(data.get("bills_df", []), ["Bill Name", "Due Date", "Amount", "Paid"])
    st.session_state["assets_df"] = records_to_dataframe(data.get("assets_df", []), ["Asset", "Value"])
    st.session_state["liabilities_df"] = records_to_dataframe(data.get("liabilities_df", []), ["Liability", "Amount"])

def save_current_user_budget():
    email = st.session_state.get("account_email", "")
    if not email:
        return False, "Please sign in first."
    get_user_save_file(email).write_text(json.dumps(get_current_budget_state(), indent=2), encoding="utf-8")
    return True, "Budget saved to your account."

def load_current_user_budget():
    email = st.session_state.get("account_email", "")
    if not email:
        return False, "Please sign in first."
    save_file = get_user_save_file(email)
    if not save_file.exists():
        return False, "No saved budget found for this account yet."
    try:
        apply_budget_state(json.loads(save_file.read_text(encoding="utf-8")))
        return True, "Saved budget loaded."
    except Exception:
        return False, "Saved budget could not be loaded."

def normalize_email(email):
    return str(email or "").lower().strip()


def ensure_user_profile(email):
    """Create a Supabase premium profile row if it does not already exist."""
    email_key = normalize_email(email)
    if not email_key:
        return

    supabase = get_supabase_client()
    if supabase is None:
        return

    try:
        existing = (
            supabase.table("user_profiles")
            .select("email")
            .eq("email", email_key)
            .eq("app", APP_NAME)
            .execute()
        )
        if not existing.data:
            supabase.table("user_profiles").insert({
                "email": email_key,
                "app": APP_NAME,
                "is_premium": False,
            }).execute()
    except Exception:
        # Do not block login if the profile table/policy is not ready yet.
        pass


def sign_in_with_supabase(email, password):
    """Try real Supabase Auth first. Returns (ok, message)."""
    email_key = normalize_email(email)
    if not email_key or not password:
        return False, "Invalid email or password."

    supabase = get_supabase_client()
    if supabase is None:
        return False, "Supabase is not connected."

    try:
        result = supabase.auth.sign_in_with_password({
            "email": email_key,
            "password": password,
        })
        if getattr(result, "user", None) or getattr(result, "session", None):
            ensure_user_profile(email_key)
            st.session_state["account_logged_in"] = True
            st.session_state["account_email"] = email_key
            st.session_state["user_email"] = email_key
            sync_premium_from_supabase(email_key)
            return True, "Signed in successfully."
    except Exception as e:
        error_text = str(e).lower()
        if "email not confirmed" in error_text or "confirm" in error_text:
            return False, "Please confirm your email first, or disable Confirm email in Supabase Auth settings for testing."
        return False, "Invalid email or password."

    return False, "Invalid email or password."


def sign_up_with_supabase(email, password):
    """Create a Supabase Auth user when Supabase is available. Returns (ok, message)."""
    email_key = normalize_email(email)
    if not email_key or "@" not in email_key:
        return False, "Enter a valid email address."
    if len(str(password or "")) < 6:
        return False, "Password must be at least 6 characters."

    supabase = get_supabase_client()
    if supabase is None:
        return False, "Supabase is not connected."

    try:
        result = supabase.auth.sign_up({
            "email": email_key,
            "password": password,
        })
        ensure_user_profile(email_key)

        # If Supabase email confirmation is OFF, a session/user is usually available immediately.
        if getattr(result, "user", None) or getattr(result, "session", None):
            st.session_state["account_logged_in"] = True
            st.session_state["account_email"] = email_key
            st.session_state["user_email"] = email_key
            sync_premium_from_supabase(email_key)
            return True, "Account created and budget saved."

        return True, "Account created. Check your email if Supabase requires confirmation."
    except Exception as e:
        error_text = str(e).lower()
        if "already" in error_text or "registered" in error_text or "exists" in error_text:
            return False, "This account already exists."
        return False, "Account could not be created. Check Supabase settings and try again."


def finish_successful_login(email_key):
    st.session_state["account_logged_in"] = True
    st.session_state["account_email"] = email_key
    st.session_state["user_email"] = email_key
    sync_premium_from_supabase(email_key)
    ok, msg = load_current_user_budget()
    st.success(t("Signed in successfully."))
    if ok:
        st.info(t(msg))


def render_account_access():
    st.markdown("### " + t("Account Access"))
    if st.session_state.get("account_logged_in"):
        st.markdown(
            f"<div style='color:#0f172a;font-weight:600;'>✅ {t('Signed in as')} {st.session_state.get('account_email')}</div>",
            unsafe_allow_html=True
        )
        col_a, col_b = st.columns(2)
        with col_a:
            if st.button(t("Save Budget"), key="save_account_budget", use_container_width=True):
                ok, msg = save_current_user_budget()
                st.success(t(msg)) if ok else st.warning(t(msg))
        with col_b:
            if st.button(t("Load Budget"), key="load_account_budget", use_container_width=True):
                ok, msg = load_current_user_budget()
                st.success(t(msg)) if ok else st.warning(t(msg))
        if st.button(t("Sign Out"), key="sign_out_btn", use_container_width=True):
            st.session_state["account_logged_in"] = False
            st.session_state["account_email"] = ""
            st.session_state["user_email"] = ""
            st.session_state["user_plan"] = FREE_PLAN
            st.success(t("Signed out."))
        return

    tab_login, tab_signup = st.tabs([t("Sign In"), t("Create Account")])

    with tab_login:
        st.markdown(f"<div class='account-mini-label'>{t('Sign In')}</div>", unsafe_allow_html=True)
        login_email = st.text_input(t("Email"), key="login_email")

        # Keep Email and Password the same length.
        # Use Streamlit's built-in password field only, so the extra custom eye button does not appear.
        password = st.text_input("Password", type="password")
        login_password = st.text_input(
            t("Password"),
            type="password",
            key="login_password",
            placeholder=t("Enter your password"),
        )

        sign_col, forgot_col = st.columns([1, 1])
        with sign_col:
            sign_in_clicked = st.button(t("Sign In"), key="login_btn", use_container_width=True)
        with forgot_col:
            forgot_clicked = st.button(t("Forgot Password?"), key="forgot_password_btn", use_container_width=True)

        if forgot_clicked:
            st.info(t("Password reset is not connected yet. For now, create a new account or contact support."))

        if sign_in_clicked:
            email_key = normalize_email(login_email)
            if not email_key or "@" not in email_key or not login_password:
                st.warning(t("Enter a valid email address."))
            else:
                # 1) Try Supabase Auth first.
                supabase_ok, supabase_msg = sign_in_with_supabase(email_key, login_password)
                if supabase_ok:
                    ok, msg = load_current_user_budget()
                    st.success(t("Signed in successfully."))
                    if ok:
                        st.info(t(msg))
                else:
                    # 2) Fallback for older local accounts created by previous versions of the app.
                    users = load_users()
                    if email_key in users and users[email_key].get("password") == hash_password(login_password):
                        finish_successful_login(email_key)
                    else:
                        st.error(t(supabase_msg if supabase_msg else "Invalid email or password."))

    with tab_signup:
        st.markdown(f"<div class='account-mini-label'>{t('Create Account')}</div>", unsafe_allow_html=True)
        signup_email = st.text_input(t("Email"), key="signup_email")

        if st.button(t("Create Account"), key="signup_btn", use_container_width=True):
            email_key = normalize_email(signup_email)
            if not email_key or "@" not in email_key:
                st.warning(t("Enter a valid email address."))
            elif len(signup_password) < 6:
                st.warning(t("Password must be at least 6 characters."))
            else:
                # 1) Create in Supabase when connected.
                supabase_ok, supabase_msg = sign_up_with_supabase(email_key, signup_password)

                # 2) Also save a local fallback account so login still works during local testing.
                users = load_users()
                if email_key not in users:
                    users[email_key] = {"password": hash_password(signup_password)}
                    save_users(users)

                if supabase_ok:
                    st.session_state["account_logged_in"] = True
                    st.session_state["account_email"] = email_key
                    st.session_state["user_email"] = email_key
                    save_current_user_budget()
                    st.success(t(supabase_msg))
                elif get_supabase_client() is None:
                    # Local-only mode: useful when testing before Supabase secrets are added.
                    st.session_state["account_logged_in"] = True
                    st.session_state["account_email"] = email_key
                    st.session_state["user_email"] = email_key
                    save_current_user_budget()
                    st.success(t("Account created and budget saved."))
                else:
                    st.warning(t(supabase_msg))

# ============================================================
# PDF REPORT EXPORT
# ============================================================

def create_pdf_report(report_text):
    if SimpleDocTemplate is None:
        return None
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []
    for block in report_text.split("\n"):
        line = block.strip()
        if not line:
            story.append(Spacer(1, 10))
        elif line.lower().endswith(":") or line.upper() == "DATA REPORT":
            story.append(Paragraph(f"<b>{line}</b>", styles["Heading2"]))
        else:
            story.append(Paragraph(line, styles["BodyText"]))
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


def to_number_series(series):
    return pd.to_numeric(series, errors="coerce").fillna(0.0)


def forecast_category_spending(spent, planned):
    today = date.today()
    days_in_month = calendar.monthrange(today.year, today.month)[1]
    current_day = today.day
    daily_average = spent / current_day if current_day > 0 else 0
    forecast_total = daily_average * days_in_month
    forecast_over = forecast_total - planned
    return round(forecast_total, 2), round(forecast_over, 2)


def calculate_health_score(total_spent, total_planned, monthly_income, savings_goal):
    score = 100
    if total_planned > 0 and total_spent > total_planned:
        score -= 30
    if monthly_income > 0 and total_spent > monthly_income:
        score -= 40
    if savings_goal > 0 and monthly_income > 0 and monthly_income - total_spent < savings_goal:
        score -= 20
    return max(score, 0)


def get_summary_df():
    budget_df = st.session_state["budget_df"]
    expense_df = st.session_state["expense_df"]
    summary = []
    if budget_df.empty:
        return pd.DataFrame(columns=["Category", "Planned", "Spent", "Remaining", "Used %", "Forecast Total", "Forecast Over", "Status"])

    safe_expenses = expense_df.copy()
    if not safe_expenses.empty and "Amount" in safe_expenses.columns:
        safe_expenses["Amount"] = to_number_series(safe_expenses["Amount"])

    for _, row in budget_df.iterrows():
        category = str(row.get("Category", "")).strip()
        planned = pd.to_numeric(row.get("Planned", 0.0), errors="coerce")
        planned = 0.0 if pd.isna(planned) else float(planned)
        spent = 0.0
        if not safe_expenses.empty and "Category" in safe_expenses.columns:
            spent = safe_expenses[safe_expenses["Category"] == category]["Amount"].sum()
        remaining = planned - spent
        used_percent = (spent / planned * 100) if planned > 0 else 0
        if is_premium_user():
            forecast_total, forecast_over = forecast_category_spending(spent, planned)
        else:
            forecast_total, forecast_over = 0, 0
        if used_percent >= 100:
            status = "🚨 Exceeded"
        elif used_percent >= 80:
            status = "⚠️ Close"
        elif is_premium_user() and forecast_total > planned:
            status = "🔮 Forecast Risk"
        else:
            status = "✅ On Track"
        summary.append([category, planned, spent, remaining, round(used_percent, 1), forecast_total, forecast_over, status])

    return pd.DataFrame(summary, columns=["Category", "Planned", "Spent", "Remaining", "Used %", "Forecast Total", "Forecast Over", "Status"])


def get_ai_context_line():
    return COUNTRY_CONTEXT.get(st.session_state.get("currency", "USD"), "General spending patterns apply.")


def ask_real_ai(prompt):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or OpenAI is None:
        return None
    try:
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a global personal finance assistant. Give clear, practical, non-judgmental budgeting advice. Avoid legal, tax, or investment guarantees."},
                {"role": "user", "content": prompt},
            ],
        )
        return response.choices[0].message.content
    except Exception:
        St.error(f"AI Error: {e}")
        return None

# ============================================================
# AUTO TRANSLATION SYSTEM
# ============================================================

def load_translation_memory():
    """Load permanent AI translations saved on disk."""
    try:
        if TRANSLATION_MEMORY_FILE.exists():
            data = json.loads(TRANSLATION_MEMORY_FILE.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}
    return {}


def save_translation_memory(memory):
    """Save permanent AI translations safely so the app learns over time."""
    try:
        TRANSLATION_MEMORY_FILE.write_text(
            json.dumps(memory, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass


@st.cache_data(show_spinner=False)
def ai_translate_once(text, language):
    """Only call AI when a translation is missing from static + saved memory."""
    if not text or language == "English":
        return text

    prompt = f"""
Translate this app UI text into {language}.

Rules:
- Return only the translated text.
- Keep emojis unchanged.
- Keep numbers, currency symbols, app names, and product names unchanged.
- Keep button labels short and natural.
- Do not explain.

Text:
{text}
"""

    translated = ask_real_ai(prompt)
    return translated.strip() if translated else text


def auto_translate_cached(text, language):
    """Translate missing UI text and permanently save successful AI translations.

    This gives you the best of both worlds:
    - Static dictionary = instant and polished.
    - Saved AI translation memory = fills gaps and becomes faster over time.
    """
    text = str(text)
    language = st.session_state.get("language", language or "English")

    if not text or language == "English":
        return text

    memory = load_translation_memory()
    language_memory = memory.setdefault(language, {})

    if text in language_memory:
        return language_memory[text]

    translated = ai_translate_once(text, language)

    if translated and translated != text:
        language_memory[text] = translated
        TRANSLATIONS.setdefault(language, {})[text] = translated
        save_translation_memory(memory)

    return translated if translated else text


def t(text):
    """Translate visible UI text using static translations, translation memory, then AI."""
    text = str(text)
    language = st.session_state.get("language", "English")

    if language == "English":
        return text

    translations = TRANSLATIONS.get(language, {})

    # 1. Exact static dictionary match
    if text in translations:
        return translations[text]

    # 2. Saved translation memory match
    memory = load_translation_memory()
    if language in memory and text in memory[language]:
        return memory[language][text]

    # 3. Normalize spacing for safer matching
    normalized = re.sub(r"\s+", " ", text.strip())
    if normalized in translations:
        return translations[normalized]
    if language in memory and normalized in memory[language]:
        return memory[language][normalized]

    # 4. Emoji-safe fallback: translate the plain label and preserve the emoji
    emoji_prefixes = [
        "🌐 ", "🌍 ", "🏦 ", "📊 ", "🧭 ", "🚨 ", "📝 ", "✏️ ", "➕ ",
        "💰 ", "💸 ", "🟢 ", "📈 ", "💵 ", "🧮 ", "💡 ", "📉 ", "📄 ",
        "📅 ", "🤖 ", "🩺 ", "🔍 ", "🧠 ", "🎯 ", "✅ ", "🔥 ", "🧬 ",
        "💾 ", "🏆 ", "📤 ", "💳 ", "🚀 ", "📋 ", "🚦 ", "⚙️ ", "💎 ",
        "🔮 ", "🔒 ", "⚠️ ", "🚫 ", "📌 ", "🌱 ", "🛡️ ", "🐣 ", "📱 ",
        "🧹 ", "🛟 ", "🔁 ", "🔥 ", "🏆 ", "💳 ", "📤 ",
    ]
    for prefix in emoji_prefixes:
        if normalized.startswith(prefix):
            plain_text = normalized.replace(prefix, "", 1)
            if plain_text in translations:
                return prefix + translations[plain_text]
            if language in memory and plain_text in memory[language]:
                return prefix + memory[language][plain_text]
            translated_plain = auto_translate_cached(plain_text, language)
            return prefix + translated_plain if translated_plain else text

    # 5. AI fallback + permanent save
    translated = auto_translate_cached(text, language)
    return translated if translated else text

def total_expenses():
    df = st.session_state["expense_df"]
    return to_number_series(df["Amount"]).sum() if not df.empty and "Amount" in df.columns else 0.0


def total_budget():
    df = st.session_state["budget_df"]
    return to_number_series(df["Planned"]).sum() if not df.empty and "Planned" in df.columns else 0.0


init_state()
load_premium_status_for_signed_in_user()
handle_payment_return()
inject_css()
render_hero()

if st.session_state.get("account_logged_in"):
    sync_premium_from_supabase(
        st.session_state.get("account_email")
    )

if st.session_state.get("account_logged_in"):
    sync_premium_from_supabase(st.session_state.get("account_email"))

with st.sidebar:
    st.markdown(
        f"""
        <div style="padding: 12px 10px;border-radius: 16px;background: rgba(255,255,255,0.10);border: 1px solid rgba(255,255,255,0.18);margin-bottom: 12px;">
            <div style="font-size:1.05rem;font-weight:900;">{t("🌍 Global Control")}</div>
            <div style="font-size:0.78rem;opacity:0.85;">{t("Language, currency, tools, and plan")}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    current_language = st.session_state.get("language", "English")
    if current_language not in LANGUAGES:
        current_language = "English"

    st.selectbox(
        t("🌐 Language"),
        LANGUAGES,
        index=LANGUAGES.index(current_language),
        key="language",
    )
    
    currency_codes = list(SUPPORTED_CURRENCIES.keys())
    current_currency = st.session_state.get("currency", "USD")
    current_base = st.session_state.get("base_currency", "USD")
    if current_currency not in currency_codes:
        current_currency = "USD"
    if current_base not in currency_codes:
        current_base = "USD"

    st.session_state["currency"] = st.selectbox(
        t("🌍 Display Currency"),
        currency_codes,
        index=currency_codes.index(current_currency),
        format_func=lambda code: f"{code} — {SUPPORTED_CURRENCIES[code]['name']}",
    )

    st.session_state["base_currency"] = st.selectbox(
        t("🏦 Base Currency"),
        currency_codes,
        index=currency_codes.index(current_base),
        format_func=lambda code: f"{code} — {SUPPORTED_CURRENCIES[code]['name']}",
        help=t("This is the currency you use when typing income, budgets, expenses, bills, assets, and debts."),
    )

    st.markdown("---")
    render_account_access()

    st.markdown("---")

    section = st.selectbox(t("Choose Section"), list(PAGE_OPTIONS.keys()), format_func=page_label)
    if len(PAGE_OPTIONS[section]) == 1:
        sidebar_page = PAGE_OPTIONS[section][0]
    else:
        sidebar_page = st.selectbox(t(strip_emoji_prefix(section)), PAGE_OPTIONS[section], format_func=page_label)

    if "active_page" not in st.session_state:
        st.session_state["active_page"] = sidebar_page
    if sidebar_page != st.session_state.get("last_sidebar_page"):
        st.session_state["active_page"] = sidebar_page
        st.session_state["last_sidebar_page"] = sidebar_page

    st.markdown("---")
    plan = t("Premium") if is_premium_user() else t("Free Plan")
    plan_col, upgrade_col = st.columns([1.2, 1])
    with plan_col:
        st.markdown(f"<div class='sidebar-plan-line'>{t('Plan')}: {plan}</div>", unsafe_allow_html=True)
    with upgrade_col:
        if not is_premium_user():
            if st.button(t("Upgrade to Premium"), key="sidebar_upgrade_to_premium", use_container_width=True):
                st.session_state["active_page"] = "💎 Upgrade"
                st.rerun()
        else:
            st.success(t("Premium"))

    st.markdown("---")
    with st.expander(t("🧹 Reset & Cleanup"), expanded=False):
        if st.button(t("Clear Expenses")):
            st.session_state["expense_df"] = pd.DataFrame(columns=["Date", "Category", "Description", "Amount"])
            st.success(t("Expenses cleared."))

        if st.button(t("Reset App")):
            st.session_state["budget_df"] = pd.DataFrame(columns=["Category", "Planned"])
            st.session_state["expense_df"] = pd.DataFrame(columns=["Date", "Category", "Description", "Amount"])
            st.session_state["bills_df"] = pd.DataFrame(columns=["Bill Name", "Due Date", "Amount", "Paid"])
            st.session_state["assets_df"] = pd.DataFrame(columns=["Asset", "Value"])
            st.session_state["liabilities_df"] = pd.DataFrame(columns=["Liability", "Amount"])
            st.session_state["savings_goal"] = 0.0
            st.session_state["monthly_income"] = 0.0
            st.session_state["user_plan"] = FREE_PLAN
            st.success(t("App reset complete."))


inject_language_direction_css()

page = st.session_state.get("active_page", "📊 Dashboard")
page = render_quick_navigation(page)
st.session_state["active_page"] = page

if page == "📊 Dashboard":
    st.subheader(t("Budget Overview"))
    budget_df = st.session_state["budget_df"]

    if budget_df.empty:
        render_empty_dashboard()
    else:
        summary_df = get_summary_df()
        total_planned = summary_df["Planned"].sum()
        total_spent = summary_df["Spent"].sum()
        total_remaining = summary_df["Remaining"].sum()
        monthly_income = st.session_state.get("monthly_income", 0.0)

        render_command_center(summary_df, total_planned, total_spent, total_remaining, monthly_income)

        st.markdown("### " + t("📊 Financial Overview"))
        col1, col2, col3 = st.columns(3)
        col1.metric(t("💰 Total Budget"), money(total_planned))
        col2.metric(t("💸 Total Spent"), money(total_spent))
        col3.metric(t("🟢 Remaining"), money(total_remaining))

        if monthly_income > 0:
            left_after_spending = monthly_income - total_spent
            savings_rate = (left_after_spending / monthly_income) * 100
            st.markdown("### " + t("📈 Income Snapshot"))
            col4, col5 = st.columns(2)
            col4.metric(t("💵 Income Left"), money(left_after_spending))
            col5.metric(t("📊 Savings Rate"), f"{savings_rate:.1f}%")

        health_score = calculate_health_score(total_spent, total_planned, monthly_income, st.session_state.get("savings_goal", 0.0))
        st.markdown("### " + t("🧭 Financial Health Score"))
        st.progress(health_score / 100)
        if health_score >= 90:
            st.success(f"{t('Excellent financial health')}: {health_score}/100")
        elif health_score >= 70:
            st.info(f"{t('Good financial health')}: {health_score}/100")
        elif health_score >= 50:
            st.warning(f"{t('Caution zone')}: {health_score}/100")
        else:
            st.error(f"{t('High financial risk')}: {health_score}/100")
        
        if not st.session_state.get("premium_trial_used", False) and not is_premium_user():
            if st.button(t("Start 1 Free Trial"), key="start_free_trial", use_container_width=True):
                activate_one_free_trial()
                st.success(t("Your free trial is active. Premium tools are unlocked for this session."))
                st.rerun()
        elif st.session_state.get("premium_trial_used", False) and not is_premium_user():
            st.info(t("Your free trial has already been used. Upgrade to continue."))

        st.markdown("### " + t("📊 Category Summary"))
        display_summary = summary_df.copy()
        for col in ["Planned", "Spent", "Remaining"]:
            display_summary[col] = display_summary[col].apply(money)
        if is_premium_user():
            display_summary["Forecast Total"] = display_summary["Forecast Total"].apply(money)
            display_summary["Forecast Over"] = display_summary["Forecast Over"].apply(money)
        else:
            display_summary["Forecast Total"] = "🔒 Premium"
            display_summary["Forecast Over"] = "🔒 Premium"
        st.dataframe(display_summary, use_container_width=True)

        st.markdown("### " + t("🚨 Smart Alerts Center"))
        alert_found = False
        for _, row in summary_df.iterrows():
            category, status, used, remaining = row["Category"], row["Status"], row["Used %"], row["Remaining"]
            if status == "🚨 Exceeded":
                alert_found = True
                st.error(f"🚨 {category}: {t('Budget exceeded by')} {money(abs(remaining))}. {t('Immediate adjustment recommended.')}")
            elif status == "⚠️ Close":
                alert_found = True
                st.warning(f"⚠️ {category}: {t('You have used')} {used}% {t('of this budget.')} {t('Slow down before exceeding your limit.')}")
            elif status == "🔮 Forecast Risk":
                alert_found = True
                st.warning(f"🔮 {category}: {t('Forecast shows possible overspending.')} {t('Projected overage')}: {money(row['Forecast Over'])}.")
        if not alert_found:
            st.success(t("✅ No major budget risks detected. Your spending looks controlled."))
        section_card(t("🌍 Global Context"), get_ai_context_line())


elif page == "📝 Budget Planner":
    st.subheader(t("📝 Set Monthly Budget"))
    st.markdown("### " + t("Quick Start Budget Templates"))

    if st.button(t("Load Basic Monthly Categories")):
        st.session_state["budget_df"] = pd.DataFrame(
            [["Housing", 0.0], ["Food", 0.0], ["Transportation", 0.0], ["Utilities", 0.0],
             ["Debt Payments", 0.0], ["Savings", 0.0], ["Health", 0.0], ["Entertainment", 0.0],
             ["Shopping", 0.0], ["Family Support", 0.0], ["Education", 0.0], ["Other", 0.0]],
            columns=["Category", "Planned"],
        )
        st.success(t("Default budget categories loaded."))

    st.markdown("### " + t("✏️ Edit Budget Categories"))
    edited_df = st.data_editor(st.session_state["budget_df"], num_rows="dynamic", use_container_width=True, key="budget_editor")
    if "Planned" in edited_df.columns:
        edited_df["Planned"] = to_number_series(edited_df["Planned"])
    if "Category" in edited_df.columns and edited_df["Category"].duplicated().any():
        st.warning(t("Duplicate categories detected. Please fix them."))
    else:
        st.session_state["budget_df"] = edited_df

    st.markdown("### " + t("➕ Add One Budget Category"))
    with st.form("budget_form"):
        category = st.text_input(t("Category"))
        planned = st.number_input(t("Planned Amount"), min_value=0.0)
        submit = st.form_submit_button(t("Add Budget"))
        if submit and category:
            st.session_state["budget_df"] = pd.concat([st.session_state["budget_df"], pd.DataFrame([[category, planned]], columns=["Category", "Planned"])], ignore_index=True)
            st.success(t("Budget added."))


elif page == "💸 Expense Tracker":
    st.subheader(t("Track Expenses"))
    categories = st.session_state["budget_df"]["Category"].dropna().tolist()
    if not categories:
        st.warning(t("Create budget categories first."))
    else:
        with st.form("expense_form"):
            expense_date = st.date_input(t("Date"))
            category = st.selectbox(t("Category"), categories)
            description = st.text_input(t("Description"))
            amount = st.number_input(t("Amount"), min_value=0.0)
            submit = st.form_submit_button(t("Add Expense"))
            if submit:
                new_row = pd.DataFrame([[expense_date, category, description, amount]], columns=["Date", "Category", "Description", "Amount"])
                st.session_state["expense_df"] = pd.concat([st.session_state["expense_df"], new_row], ignore_index=True)
                st.success(t("Expense added."))

    display_expenses = st.session_state["expense_df"].copy()
    if not display_expenses.empty and "Amount" in display_expenses.columns:
        display_expenses["Amount"] = to_number_series(display_expenses["Amount"]).apply(money)
    st.dataframe(display_expenses, use_container_width=True)


elif page == "💵 Income":
    st.subheader(t("Monthly Income"))
    income = st.number_input(t("Enter your monthly income"), min_value=0.0, value=float(st.session_state["monthly_income"]))
    if st.button(t("Save Income")):
        st.session_state["monthly_income"] = income
        st.success(t("Monthly income saved."))
    st.info(f"{t('Current saved income')}: {money(st.session_state['monthly_income'])}")


elif page == "🎯 Savings Goal":
    st.subheader(t("Savings Goal"))
    goal = st.number_input(t("How much do you want to save this month?"), min_value=0.0, value=float(st.session_state["savings_goal"]))
    if st.button(t("Save Goal")):
        st.session_state["savings_goal"] = goal
        st.success(t("Savings goal saved."))
    st.info(f"{t('Current savings goal')}: {money(st.session_state['savings_goal'])}")


elif page == "🧮 Can I Afford This?":
    st.subheader(t("🧮 Can I Afford This?"))
    amount = st.number_input(t("Enter amount you want to spend"), min_value=0.0)
    monthly_income = st.session_state.get("monthly_income", 0.0)
    savings_goal = st.session_state.get("savings_goal", 0.0)
    total_spent = total_expenses()
    remaining_income = monthly_income - total_spent
    remaining_after_purchase = remaining_income - amount
    st.markdown("### " + t("💡 Decision"))
    if monthly_income == 0:
        st.warning(t("Please set your income first."))
    elif remaining_after_purchase < 0:
        st.error(t("🚫 You cannot afford this. It exceeds your available income."))
    elif savings_goal > 0 and remaining_after_purchase < savings_goal:
        st.warning(f"⚠️ {t('This purchase may affect your savings goal.')} {t('You will have')} {money(remaining_after_purchase)} {t('left')}.")
    else:
        st.success(f"✅ {t('You can afford this.')} {t('You will still have')} {money(remaining_after_purchase)} {t('remaining')}.")
    st.markdown("### " + t("📊 Summary"))
    st.write(f"{t('Income')}: {money(monthly_income)}")
    st.write(f"{t('Spent so far')}: {money(total_spent)}")
    st.write(f"{t('Remaining income')}: {money(remaining_income)}")


elif page == "🚨 Bill Reminder Center":
    st.subheader(t("🚨 Bill Reminder Center"))
    st.markdown("### " + t("➕ Add Bill"))
    with st.form("bill_form"):
        bill_name = st.text_input(t("Bill Name"))
        due_date = st.date_input(t("Due Date"))
        amount = st.number_input(t("Bill Amount"), min_value=0.0)
        paid = st.checkbox(t("Already Paid?"))
        submit = st.form_submit_button(t("Add Bill"))
        if submit and bill_name:
            new_bill = pd.DataFrame([[bill_name, due_date, amount, paid]], columns=["Bill Name", "Due Date", "Amount", "Paid"])
            st.session_state["bills_df"] = pd.concat([st.session_state["bills_df"], new_bill], ignore_index=True)
            st.success(t("Bill added."))
    bills_df = st.session_state["bills_df"]
    st.markdown("### " + t("📋 Bills"))
    if bills_df.empty:
        st.info(t("No bills added yet."))
    else:
        edited_bills = st.data_editor(bills_df, num_rows="dynamic", use_container_width=True, key="bills_editor")
        if "Amount" in edited_bills.columns:
            edited_bills["Amount"] = to_number_series(edited_bills["Amount"])
        st.session_state["bills_df"] = edited_bills
        st.markdown("### " + t("🚦 Bill Status"))
        today = date.today()
        for _, row in edited_bills.iterrows():
            bill = row.get("Bill Name", "")
            if not bill:
                continue
            due = pd.to_datetime(row.get("Due Date", today)).date()
            amount = float(row.get("Amount", 0.0) or 0.0)
            paid = bool(row.get("Paid", False))
            days_left = (due - today).days
            if paid:
                st.success(f"✅ {bill}: {t('Paid')} — {money(amount)}")
            elif days_left < 0:
                st.error(f"🚨 {bill}: {t('Overdue by')} {abs(days_left)} {t('days')} — {money(amount)}")
            elif days_left <= 3:
                st.warning(f"⚠️ {bill}: {t('Due in')} {days_left} {t('days')} — {money(amount)}")
            else:
                st.info(f"📅 {bill}: {t('Due in')} {days_left} {t('days')} — {money(amount)}")


elif page == "🩺 Budget Doctor":
    require_premium("Budget Doctor")
    st.subheader(t("🩺 Budget Doctor"))
    budget_df, monthly_income, savings_goal = st.session_state["budget_df"], st.session_state.get("monthly_income", 0.0), st.session_state.get("savings_goal", 0.0)
    if budget_df.empty:
        st.info(t("Add your budget categories first."))
    else:
        total_b, total_s, remaining_income = total_budget(), total_expenses(), monthly_income - total_expenses()
        st.markdown("### " + t("🔍 Diagnosis"))
        if monthly_income == 0:
            st.warning(t("Income is missing. Add your monthly income so the app can judge your budget accurately."))
        if total_b > monthly_income and monthly_income > 0:
            st.error(t("Your planned budget is higher than your income. This budget may not be realistic."))
        elif monthly_income > 0:
            st.success(t("Your planned budget fits within your income."))
        if total_b > 0 and total_s > total_b:
            st.error(t("You are currently spending more than your planned budget."))
        elif total_b > 0 and total_s >= total_b * 0.8:
            st.warning(t("You are close to using your full budget."))
        else:
            st.success(t("Your spending is currently under control."))
        if savings_goal > 0 and remaining_income < savings_goal:
            st.warning(t("Your current spending may prevent you from reaching your savings goal."))
        elif savings_goal > 0:
            st.success(t("Your savings goal still looks reachable."))
        st.markdown("### " + t("🌍 Context"))
        st.write(get_ai_context_line())
        st.markdown("### " + t("🧠 Smart Recommendation"))
        if monthly_income == 0:
            st.write(t("Start by entering your monthly income."))
        elif total_b > monthly_income:
            st.write(t("Reduce planned spending categories until your total budget is below your income."))
        elif total_b > 0 and total_s > total_b:
            st.write(t("Pause non-essential spending and review the categories where you went over budget."))
        elif savings_goal > 0 and remaining_income < savings_goal:
            st.write(t("Cut flexible categories like shopping, entertainment, or dining out."))
        else:
            st.write(t("Your budget looks healthy. Keep tracking expenses consistently."))

elif page == "🤖 AI Budget Generator":
    st.subheader(t("AI Budget Generator"))

    income = st.session_state.get("monthly_income", 0)

    if income == 0:
        st.warning(t("Add your income first"))
    else:
        if st.button(t("Generate Budget Plan")):
            prompt = f"Create a simple monthly budget for income {income} in {st.session_state['currency']}"
            response = ask_real_ai(prompt)

            if response:
                st.write(response)
            else:
                st.info(t("AI not connected"))

elif page == "🧠 What Changed?":
    st.subheader(t("🧠 What Changed This Month?"))
    expense_df = st.session_state["expense_df"]
    if expense_df.empty:
        st.info(t("Add expenses first so the app can detect changes."))
    else:
        safe_expenses = expense_df.copy()
        safe_expenses["Amount"] = to_number_series(safe_expenses["Amount"])
        category_spending = safe_expenses.groupby("Category")["Amount"].sum().sort_values(ascending=False)
        st.markdown("### " + t("🔍 Spending Breakdown"))
        display_category_spending = category_spending.reset_index()
        display_category_spending["Amount"] = display_category_spending["Amount"].apply(money)
        st.dataframe(display_category_spending, use_container_width=True)
        st.markdown("### " + t("🧠 Smart Explanation"))
        top_category, top_amount, total_spent = category_spending.index[0], category_spending.iloc[0], category_spending.sum()
        top_percent = (top_amount / total_spent) * 100 if total_spent > 0 else 0
        if top_percent >= 50:
            st.warning(f"{t('Most of your money went to')} **{top_category}**, {t('which makes up')} {top_percent:.1f}% {t('of all spending.')}")
        elif top_percent >= 30:
            st.info(f"{t('Your largest category is')} **{top_category}**, {t('making up')} {top_percent:.1f}% {t('of spending')}.")
        else:
            st.success(t("Your spending is spread across categories. No single category dominates your budget."))
        st.markdown("### " + t("✅ Suggested Next Move"))
        if top_percent >= 50:
            st.write(f"{t('Review')} **{top_category}** {t('first. Even a small cut there could make a big difference.')}")
        elif top_percent >= 30:
            st.write(f"{t('Watch')} **{top_category}** {t('closely this month.')}")
        else:
            st.write(t("Keep tracking consistently. Your spending pattern looks balanced."))

elif page == "💳 Debt Payoff":
    st.subheader(t("Debt Payoff Planner"))

    df = st.data_editor(st.session_state["debts_df"], num_rows="dynamic")
    st.session_state["debts_df"] = df

    total_debt = df["Balance"].sum() if not df.empty else 0

    st.metric(t("Total Debt"), money(total_debt))

elif page == "🔥 Ask Your Money AI":
    require_premium("Ask Your Money AI")
    st.subheader(t("🔥 Ask Your Money AI"))
    st.markdown("### " + t("🌍 Context"))
    st.write(get_ai_context_line())
    question = st.text_input(t("Ask a money question"), placeholder=t("Example: Can I save 500 this month?"))
    if question:
        total_b, total_s = total_budget(), total_expenses()
        monthly_income, savings_goal = st.session_state.get("monthly_income", 0.0), st.session_state.get("savings_goal", 0.0)
        remaining_income = monthly_income - total_s
        st.markdown("### " + t("🧠 AI Answer"))
        prompt = f"Question: {question}\nLanguage: {st.session_state['language']}\nCurrency: {st.session_state['currency']}\nIncome: {monthly_income}\nBudget: {total_b}\nSpent: {total_s}\nRemaining: {remaining_income}\nSavings goal: {savings_goal}\nContext: {get_ai_context_line()}"
        real_answer = ask_real_ai(prompt)
        if real_answer:
            st.write(real_answer)
        else:
            q = question.lower()
            if monthly_income == 0:
                st.warning(t("Add your monthly income first so I can answer accurately."))
            elif "save" in q or "savings" in q:
                if savings_goal == 0:
                    st.info(t("Set a savings goal first. Right now I can only estimate your remaining income."))
                    st.write(f"{t('Remaining income')}: {money(remaining_income)}")
                elif remaining_income >= savings_goal:
                    st.success(f"{t('Yes. Based on your current spending, you have')} {money(remaining_income)} {t('left, so your savings goal still looks reachable.')}")
                else:
                    st.warning(f"{t('Your savings goal may be at risk. You have')} {money(remaining_income)} {t('left, but your goal is')} {money(savings_goal)}.")
            elif "afford" in q or "buy" in q:
                st.info(f"{t('Right now, you have about')} {money(remaining_income)} {t('available after spending')}.")
            elif "spent" in q or "spending" in q:
                st.info(f"{t('You have spent')} {money(total_s)} {t('so far this month')}.")
            elif "budget" in q:
                st.info(f"{t('Your planned budget is')} {money(total_b)}, {t('and you have spent')} {money(total_s)}.")
            else:
                st.write(f"{t('Income')}: {money(monthly_income)} | {t('Total Spent')}: {money(total_s)} | {t('Remaining')}: {money(remaining_income)}")


elif page == "🧬 Money Personality":
    st.subheader(t("🧬 Your Money Personality"))
    expense_df, monthly_income = st.session_state["expense_df"], st.session_state.get("monthly_income", 0.0)
    if expense_df.empty or monthly_income == 0:
        st.info(t("Add income and expenses to discover your money personality."))
    else:
        safe_expenses = expense_df.copy()
        safe_expenses["Amount"] = to_number_series(safe_expenses["Amount"])
        total_s = safe_expenses["Amount"].sum()
        spending_ratio = total_s / monthly_income if monthly_income > 0 else 0
        category_spending = safe_expenses.groupby("Category")["Amount"].sum().sort_values(ascending=False)
        top_category = category_spending.index[0]
        top_percent = (category_spending.iloc[0] / total_s) * 100 if total_s > 0 else 0
        st.markdown("### " + t("🔍 Analysis"))
        st.write(f"{t('Spending Ratio')}: {spending_ratio:.2f}")
        st.write(f"{t('Top Category')}: {top_category} ({top_percent:.1f}%)")
        st.markdown("### " + t("🧠 Your Type"))
        if spending_ratio >= 1:
            personality, description, advice = "🚨 The Overspender", t("You tend to spend more than you earn. High financial risk."), t("Immediate budget adjustment is critical. Focus on essentials.")
        elif spending_ratio >= 0.8:
            personality, description, advice = "⚠️ The Risk Taker", t("You spend most of your income. Little margin for savings."), t("Reduce flexible spending and build a safety buffer.")
        elif top_percent >= 50:
            personality, description, advice = "🎯 The Focused Spender", f"{t('You concentrate spending heavily on')} {top_category}.", f"{t('Optimizing')} {top_category} {t('alone could significantly improve your finances')}."
        elif spending_ratio <= 0.5:
            personality, description, advice = "💎 The Saver", t("You spend conservatively and retain a strong portion of your income."), t("Consider building an emergency fund and improving savings discipline.")
        else:
            personality, description, advice = "⚖️ The Balanced Planner", t("Your spending is controlled and well distributed."), t("Maintain consistency and monitor trends over time.")
        st.success(personality)
        st.write(description)
        st.markdown("### " + t("💡 Recommendation"))
        st.write(advice)


elif page == "🎯 Spending Challenge":
    require_premium("Spending Challenge")
    st.subheader(t("🎯 Spending Challenge Mode"))
    total_s, monthly_income, savings_goal = total_expenses(), st.session_state.get("monthly_income", 0.0), st.session_state.get("savings_goal", 0.0)
    if st.session_state["expense_df"].empty:
        st.info(t("Add expenses first so the app can create a challenge."))
    else:
        remaining_income = monthly_income - total_s if monthly_income > 0 else 0
        st.markdown("### " + t("🧠 Your Challenge"))
        if monthly_income == 0:
            st.warning(t("Add your monthly income first."))
            st.write(t("Challenge: Track every expense for the next 7 days."))
        elif savings_goal > 0 and remaining_income < savings_goal:
            st.error(t("Your savings goal is at risk."))
            st.write(t("Challenge: Reduce flexible spending by 15% this week."))
        elif total_s > monthly_income * 0.75:
            st.warning(t("You have already used more than 75% of your income."))
            st.write(t("Challenge: No non-essential spending for the next 3 days."))
        else:
            st.success(t("Your spending looks controlled."))
            st.write(f"{t('Challenge: Save an extra')} {money(25)} {t('this week')}.")
        st.markdown("### " + t("✅ Why This Helps"))
        st.write(t("Small weekly challenges make budgeting easier because they turn money management into simple actions."))


elif page == "🧠 Money Coach":
    require_premium("AI Money Coach")
    st.subheader(t("🧠 AI Money Coach"))
    if st.session_state["budget_df"].empty:
        st.info(t("Add your budget first."))
    else:
        total_b, total_s = total_budget(), total_expenses()
        used_percent = (total_s / total_b * 100) if total_b > 0 else 0
        if used_percent >= 100:
            st.error(t("You have exceeded your monthly budget."))
        elif used_percent >= 80:
            st.warning(t("You are close to your monthly budget limit."))
        else:
            st.success(t("Your spending is currently on track."))
        st.markdown("### " + t("Recommended Action"))
        st.write(t("Review high-spending categories and reduce non-essential expenses."))


elif page == "📄 Data Report":
    st.subheader(t("Data Report"))
    budget_df, monthly_income, savings_goal = st.session_state["budget_df"], st.session_state.get("monthly_income", 0.0), st.session_state.get("savings_goal", 0.0)
    if budget_df.empty:
        st.info(t("Add budget categories first."))
    else:
        total_b, total_s = total_budget(), total_expenses()
        report_text = f"""
DATA REPORT

Currency: {st.session_state["currency"]}
Income: {money(monthly_income)}
Total Planned Budget: {money(total_b)}
Total Spent: {money(total_s)}
Remaining Budget: {money(total_b - total_s)}
Income Left After Spending: {money(monthly_income - total_s if monthly_income > 0 else 0.0)}
Savings Goal: {money(savings_goal)}

SUMMARY:
This report gives a clean snapshot of your monthly budget, spending, remaining funds, and savings goal progress.

RECOMMENDATION:
Review your highest spending categories and reduce non-essential expenses if your remaining budget or savings goal is at risk.
"""
        st.text_area(t("Report Preview"), report_text, height=350)
        st.download_button(label=t("Download Data Report"), data=report_text, file_name="data_report.txt", mime="text/plain")
        pdf_bytes = create_pdf_report(report_text)
        if pdf_bytes:
            st.download_button(label=t("Download PDF Report"), data=pdf_bytes, file_name="explainmybudget_report.pdf", mime="application/pdf")
        else:
            st.info(t("PDF export needs ReportLab. Install it with: pip install reportlab"))


elif page == "🔁 Subscriptions":
    st.subheader(t("Subscription Tracker"))

    df = st.data_editor(st.session_state["subscriptions_df"], num_rows="dynamic")
    st.session_state["subscriptions_df"] = df

    total = df["Cost"].sum() if not df.empty else 0
    st.metric(t("Monthly Subscriptions"), money(total))


elif page == "🛟 Emergency Fund":
    st.subheader(t("Emergency Fund"))

    expenses = total_expenses()

    months = st.slider(t("Months of coverage"), 1, 12, 3)

    target = expenses * months

    st.metric(t("Target Fund"), money(target))

elif page == "📅 AI Insights Report":
    require_premium("AI Insights Report")
    st.subheader(t("📅 AI Insights Report"))
    monthly_income, savings_goal = st.session_state.get("monthly_income", 0.0), st.session_state.get("savings_goal", 0.0)
    if page == "📅 AI Insights Report":
        require_premium("AI Insights Report")
        render_ai_insights_report()
    if monthly_income == 0:
        st.warning(t("Add your monthly income to generate a full report."))
    else:
        total_b, total_s = total_budget(), total_expenses()
        remaining_income = monthly_income - total_s
        expense_df = st.session_state["expense_df"]
        if not expense_df.empty:
            safe = expense_df.copy()
            safe["Amount"] = to_number_series(safe["Amount"])
            cats = safe.groupby("Category")["Amount"].sum().sort_values(ascending=False)
            top_category, top_amount = cats.index[0], cats.iloc[0]
        else:
            top_category, top_amount = "N/A", 0.0
        if total_s > monthly_income:
            tone = t("⚠️ You are currently spending more than your income.")
            recommendation = t("Reduce non-essential spending immediately and rebalance your budget.")
        elif total_b > 0 and total_s > total_b:
            tone = t("⚠️ You have exceeded your planned budget.")
            recommendation = t("Adjust your planned budget or cut spending in key categories.")
        elif savings_goal > 0 and remaining_income < savings_goal:
            tone = t("⚠️ Your savings goal is at risk.")
            recommendation = t("Focus on reducing flexible expenses like shopping or entertainment.")
        else:
            tone = t("✅ Your financial situation looks stable.")
            recommendation = t("Continue tracking your expenses and consider increasing your savings goal.")
        report = f"""
**Currency:** {st.session_state["currency"]}  
**Income:** {money(monthly_income)}  
**Total Spending:** {money(total_s)}  
**Planned Budget:** {money(total_b)}  
**Remaining Income:** {money(remaining_income)}  
**Top Spending Category:** {top_category} ({money(top_amount)})  

### 🌍 {t("Global Context")}
{get_ai_context_line()}

### 📊 {t("Analysis")}
{tone}

### 📌 {t("Key Insight")}
{t("Most of your money is going toward")} **{top_category}**, {t("which is influencing your overall financial behavior.")}

### 💡 {t("Recommendation")}
{recommendation}
"""
        st.markdown(report)
        if st.button(t("Generate Real AI Response")):
            ai_response = ask_real_ai(f"Language: {st.session_state['language']}\n{report}")
            if ai_response:
                st.markdown("### " + t("🤖 Real AI Response"))
                st.write(ai_response)
            else:
                st.info(t("Real AI is not connected yet. Add OPENAI_API_KEY to your environment to activate it."))
        st.download_button(label=t("Download AI Insights Report"), data=report, file_name="ai_insights_report.txt", mime="text/plain")

elif page == "🛟 Emergency Fund":
    st.subheader(t("Emergency Fund"))

    expenses = total_expenses()

    months = st.slider(t("Months of coverage"), 1, 12, 3)

    target = expenses * months

    st.metric(t("Target Fund"), money(target))

elif page == "📥 Import Bank CSV":
    st.subheader(t("Import Transactions"))

    file = st.file_uploader("Upload CSV")

    if file:
        df = pd.read_csv(file)

        if "Amount" in df.columns:
            st.session_state["expense_df"] = df
            st.success(t("Imported successfully"))
        else:
            st.error(t("Invalid format"))

elif page == "🎯 Goals":
    st.subheader(t("Goals Dashboard"))

    df = st.data_editor(st.session_state["goals_df"], num_rows="dynamic")
    st.session_state["goals_df"] = df

    for _, row in df.iterrows():
        progress = row["Saved"] / row["Target"] if row["Target"] else 0
        st.progress(progress)

elif page == "📤 Money Snapshot":
    st.subheader(t("📤 Shareable Money Snapshot"))
    monthly_income, savings_goal = st.session_state.get("monthly_income", 0.0), st.session_state.get("savings_goal", 0.0)
    total_b, total_s = total_budget(), total_expenses()
    remaining_income = monthly_income - total_s if monthly_income > 0 else 0.0
    if monthly_income == 0:
        st.warning(t("Add your income first to create a complete snapshot."))
    else:
        snapshot = f"""
💰 ExplainMyBudget AI Snapshot

Currency: {st.session_state["currency"]}
Income: {money(monthly_income)}
Planned Budget: {money(total_b)}
Spent So Far: {money(total_s)}
Remaining Income: {money(remaining_income)}
Savings Goal: {money(savings_goal)}

Quick Insight:
"""
        if total_s > monthly_income:
            snapshot += t("You are spending more than your income. Immediate action is needed.")
        elif savings_goal > 0 and remaining_income < savings_goal:
            snapshot += t("Your savings goal may be at risk. Reduce flexible spending.")
        elif total_b > 0 and total_s > total_b:
            snapshot += t("You are over your planned budget. Review high-spending categories.")
        else:
            snapshot += t("Your budget looks stable right now.")
        st.text_area(t("Copy Your Snapshot"), snapshot, height=280)
        st.download_button(label=t("Download Snapshot"), data=snapshot, file_name="money_snapshot.txt", mime="text/plain")


elif page == "💾 Backup & Restore":
    st.subheader(t("💾 Backup & Restore"))
    budget_df, expense_df = st.session_state["budget_df"], st.session_state["expense_df"]
    st.markdown("### " + t("Download Your Data"))
    if not budget_df.empty:
        st.download_button(label=t("Download Budget CSV"), data=budget_df.to_csv(index=False), file_name="budget_backup.csv", mime="text/csv")
    if not expense_df.empty:
        st.download_button(label=t("Download Expenses CSV"), data=expense_df.to_csv(index=False), file_name="expenses_backup.csv", mime="text/csv")
    st.markdown("### " + t("Restore Budget Data"))
    budget_file = st.file_uploader(t("Upload Budget CSV"), type=["csv"], key="budget_restore")
    if budget_file is not None:
        restored_budget = pd.read_csv(budget_file)
        if "Category" in restored_budget.columns and "Planned" in restored_budget.columns:
            st.session_state["budget_df"] = restored_budget
            st.success(t("Budget data restored."))
        else:
            st.error(t("Invalid budget file. It must include Category and Planned columns."))
    st.markdown("### " + t("Restore Expenses Data"))
    expense_file = st.file_uploader(t("Upload Expenses CSV"), type=["csv"], key="expense_restore")
    if expense_file is not None:
        restored_expenses = pd.read_csv(expense_file)
        required_cols = ["Date", "Category", "Description", "Amount"]
        if all(col in restored_expenses.columns for col in required_cols):
            st.session_state["expense_df"] = restored_expenses
            st.success(t("Expense data restored."))
        else:
            st.error(t("Invalid expenses file. It must include Date, Category, Description, and Amount columns."))


elif page == "📈 Spending Patterns":
    st.subheader(t("📈 Spending Pattern Detection"))
    expense_df = st.session_state["expense_df"]
    if expense_df.empty:
        st.info(t("Add expenses first to detect patterns."))
    else:
        safe = expense_df.copy()
        safe["Amount"] = to_number_series(safe["Amount"])
        category_spending = safe.groupby("Category")["Amount"].sum().sort_values(ascending=False)
        st.markdown("### " + t("Top Spending Categories"))
        st.bar_chart(category_spending)
        top_category, top_amount, total_s = category_spending.index[0], category_spending.iloc[0], safe["Amount"].sum()
        top_percent = (top_amount / total_s) * 100 if total_s > 0 else 0
        st.markdown("### " + t("Smart Insight"))
        if top_percent >= 50:
            st.warning(f"{top_category} {t('represents')} {top_percent:.1f}% {t('of your total spending. This category may be controlling your budget.')}")
        elif top_percent >= 30:
            st.info(f"{top_category} {t('is your largest spending category at')} {top_percent:.1f}%.")
        else:
            st.success(t("Your spending appears fairly balanced across categories."))


elif page == "📉 Spending Trends":
    st.subheader(t("📉 Spending Trends Over Time"))
    expense_df = st.session_state["expense_df"].copy()
    if expense_df.empty:
        st.info(t("Add expenses first to see trends."))
    else:
        expense_df["Date"] = pd.to_datetime(expense_df["Date"])
        expense_df["Amount"] = to_number_series(expense_df["Amount"])
        daily_spending = expense_df.groupby("Date")["Amount"].sum()
        st.markdown("### " + t("Daily Spending"))
        st.line_chart(daily_spending)
        st.markdown("### " + t("Trend Insight"))
        if len(daily_spending) >= 2:
            if daily_spending.iloc[-1] > daily_spending.iloc[0]:
                st.warning(t("Your spending trend is increasing. Watch your pace."))
            elif daily_spending.iloc[-1] < daily_spending.iloc[0]:
                st.success(t("Your spending trend is decreasing. Good control."))
            else:
                st.info(t("Your spending trend is stable."))
        else:
            st.info(t("Add more expense dates to detect a trend."))


elif page == "🏆 Money Rewards":
    st.subheader(t("🏆 Money Rewards"))
    budget_df, expense_df = st.session_state["budget_df"], st.session_state["expense_df"]
    monthly_income, savings_goal = st.session_state.get("monthly_income", 0.0), st.session_state.get("savings_goal", 0.0)
    points, badges = 0, []
    if monthly_income > 0:
        points += 20; badges.append("💵 Income Set")
    if not budget_df.empty:
        points += 25; badges.append("📝 Budget Builder")
    if not expense_df.empty:
        points += 25; badges.append("💸 Expense Tracker")
    total_s = total_expenses()
    remaining_income = monthly_income - total_s if monthly_income > 0 else 0.0
    if savings_goal > 0:
        points += 20; badges.append("🎯 Goal Setter")
    if monthly_income > 0 and remaining_income >= savings_goal and savings_goal > 0:
        points += 30; badges.append("💎 Savings Protector")
    if monthly_income > 0 and total_s <= monthly_income:
        points += 30; badges.append("🛡️ Budget Defender")
    if points >= 120:
        level = "🏆 Level 5 — Money Master"
    elif points >= 90:
        level = "🔥 Level 4 — Smart Planner"
    elif points >= 60:
        level = "🌱 Level 3 — Budget Builder"
    elif points >= 30:
        level = "🚀 Level 2 — Getting Started"
    else:
        level = "🐣 Level 1 — New Tracker"
    st.markdown("### " + t("Your Level"))
    st.success(level)
    st.markdown("### " + t("Points"))
    st.progress(min(points, 120) / 120)
    st.write(f"**{points} / 120 points**")
    st.markdown("### " + t("Badges Earned"))
    if badges:
        for badge in badges:
            st.write(badge)
    else:
        st.info(t("Start by adding income, budget categories, or expenses to earn badges."))
    st.markdown("### " + t("Next Best Action"))
    if monthly_income == 0:
        st.write(t("Add your monthly income to earn your first badge."))
    elif budget_df.empty:
        st.write(t("Create your first budget category."))
    elif expense_df.empty:
        st.write(t("Track your first expense."))
    elif savings_goal == 0:
        st.write(t("Set a savings goal to unlock another badge."))
    else:
        st.write(t("Keep tracking consistently to protect your budget streak."))


elif page == "📊 Net Worth":
    st.subheader(t("📊 Net Worth Tracker"))
    st.markdown("### " + t("💰 Assets"))
    assets_df = st.data_editor(st.session_state["assets_df"], num_rows="dynamic", use_container_width=True, key="assets_editor")
    if "Value" in assets_df.columns:
        assets_df["Value"] = to_number_series(assets_df["Value"])
    st.session_state["assets_df"] = assets_df
    st.markdown("### " + t("💳 Liabilities"))
    liabilities_df = st.data_editor(st.session_state["liabilities_df"], num_rows="dynamic", use_container_width=True, key="liabilities_editor")
    if "Amount" in liabilities_df.columns:
        liabilities_df["Amount"] = to_number_series(liabilities_df["Amount"])
    st.session_state["liabilities_df"] = liabilities_df
    total_assets = assets_df["Value"].sum() if not assets_df.empty and "Value" in assets_df.columns else 0.0
    total_liabilities = liabilities_df["Amount"].sum() if not liabilities_df.empty and "Amount" in liabilities_df.columns else 0.0
    net_worth = total_assets - total_liabilities
    st.markdown("### " + t("📊 Summary"))
    col1, col2, col3 = st.columns(3)
    col1.metric(t("Total Assets"), money(total_assets))
    col2.metric(t("Total Liabilities"), money(total_liabilities))
    col3.metric(t("Net Worth"), money(net_worth))
    st.markdown("### " + t("🧠 Insight"))
    if net_worth < 0:
        st.error(t("Your liabilities exceed your assets. Focus on reducing debt."))
    elif total_assets > 0 and net_worth < total_assets * 0.3:
        st.warning(t("Your net worth is positive but relatively low compared to your assets."))
    else:
        st.success(t("Your net worth is in a healthy range."))
    st.markdown("### " + t("📈 Growth Tip"))
    if total_liabilities > total_assets:
        st.write(t("Prioritize paying down high-interest debt first."))
    else:
        st.write(t("Consider growing assets through savings or investments."))


elif page == "⚙️ Settings":
    st.subheader(t("⚙️ Settings"))
    st.info(t("Use the sidebar to change language, currency, section, and plan."))
    st.markdown("### " + t("Current Settings"))
    st.write(f"{t('Language')}: **{st.session_state['language']}**")
    st.write(f"{t('Display Currency')}: **{st.session_state['currency']}**")
    st.write(f"{t('Base Currency')}: **{st.session_state['base_currency']}**")
    st.write(f"{t('Plan')}: **{'Premium' if is_premium_user() else 'Free Plan'}**")

elif page == "💎 Upgrade":
    render_stripe_upgrade_page()

render_footer()
