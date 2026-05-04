import os

import stripe
from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException
from supabase import create_client

load_dotenv()

app = FastAPI()

STRIPE_WEBROOK_SECRET_KEY=whsec_b16b5b5beda57015108cc6e51671d0c0a34a020fdee5c7c6ca093a0758de5c46
SUPABASE_ANON_KEY=sb_publishable_Y8oIl_r9yNIJb8us5BoEcA_q92gfImy 
SUPABASE_URL=https://geqlzmgmzisuythzausr.supabase.co 

"email": email.lower().strip(),
"app": "ExplainMyBudget",
"is_premium": True,

SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY")
APP_NAME = os.getenv("APP_NAME", "ExplainMyBudget")
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = (
    os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    or os.getenv("SUPABASE_ANON_KEY")
)

if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY

supabase = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None


def normalize_email(value: str) -> str:
    return (value or "").lower().strip()


def set_user_premium(email: str, is_premium: bool, plan_source: str):
    email = normalize_email(email)
    if not email or supabase is None:
        return

    payload = {
        "email": email,
        "app": APP_NAME,
        "is_premium": is_premium,
        "plan_source": plan_source,
    }

    try:
        existing = (
            supabase.table("user_profiles")
            .select("email")
            .eq("email", email)
            .eq("app", APP_NAME)
            .execute()
        )

        if existing.data:
            supabase.table("user_profiles") \
                .update({"is_premium": is_premium, "plan_source": plan_source}) \
                .eq("email", email) \
                .eq("app", APP_NAME) \
                .execute()
        else:
            supabase.table("user_profiles").insert(payload).execute()
    except Exception as e:
        print("Supabase premium update failed:", e)


@app.post("/stripe-webhook")
async def stripe_webhook(request: Request):
    if not STRIPE_WEBHOOK_SECRET:
        raise HTTPException(status_code=500, detail="STRIPE_WEBHOOK_SECRET is missing")

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=sig_header,
            secret=STRIPE_WEBHOOK_SECRET,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    event_type = event["type"]
    obj = event["data"]["object"]

    if event_type == "checkout.session.completed":
        email = normalize_email(
            obj.get("customer_email")
            or obj.get("client_reference_id")
            or obj.get("metadata", {}).get("email")
        )
        mode = obj.get("mode")

        if mode == "payment":
            # One-time access: premium stays true permanently.
            set_user_premium(email, True, "stripe_one_time")

        elif mode == "subscription":
            # Monthly subscription: premium is true when subscription starts.
            set_user_premium(email, True, "stripe_monthly_subscription")

    elif event_type == "customer.subscription.deleted":
        customer_id = obj.get("customer")
        email = ""
        try:
            customer = stripe.Customer.retrieve(customer_id)
            email = normalize_email(customer.get("email"))
        except Exception:
            pass

        if email:
            # Monthly ended/cancelled. One-time buyers should not be connected to this event.
            #set_user_premium(email, False, "stripe_subscription_cancelled")

    elif event_type == "invoice.payment_failed":
        customer_id = obj.get("customer")
        email = ""
        try:
            customer = stripe.Customer.retrieve(customer_id)
            email = normalize_email(customer.get("email"))
        except Exception:
            pass

        if email:
            #set_user_premium(email, False, "stripe_invoice_payment_failed")

    return {"received": True}



