from fastapi import FastAPI, HTTPException, Depends, Security, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, validator
from datetime import datetime
import httpx
import os
import json
from sqlalchemy import create_engine, Column, String, Integer, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from typing import Optional, List, Dict, Any
import re
import hmac
import hashlib
import logging

from aiogram import Bot
import os
from dotenv import load_dotenv

load_dotenv()  # Load the environment variables from the .env file

bot = Bot(token=os.getenv("TELEGRAM_BOT_TOKEN"))  # Create the bot instance with the token


# Configure logging
logging.basicConfig(level=logging.INFO)

app = FastAPI()
security = HTTPBearer()

# Database setup
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is required")

# Fix PostgreSQL URL format for SQLAlchemy 2.0
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg2://")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Database model for storing integrations
class Integration(Base):
    __tablename__ = "integrations"
    
    id = Column(Integer, primary_key=True, index=True)
    github_repo = Column(String, index=True)
    chat_id = Column(String)
    created_at = Column(String, default=lambda: datetime.utcnow().isoformat())
    api_key = Column(String, unique=True)

# Create tables
Base.metadata.create_all(bind=engine)

# Pydantic models for GitHub webhook payload
class RepositoryInfo(BaseModel):
    full_name: str
    id: int

    @validator("full_name")
    def validate_full_name(cls, v):
        if not re.match(r"^[a-zA-Z0-9-_]+/[a-zA-Z0-9-_]+$", v):
            raise ValueError("Invalid repository format. Expected format: username/repository_name")
        return v

class CommitInfo(BaseModel):
    id: str
    message: str
    timestamp: str
    url: str
    author: Dict[str, Any]

class PusherInfo(BaseModel):
    name: str
    email: Optional[str] = None
    
class UserInfo(BaseModel):
    login: str

class BranchInfo(BaseModel):
    ref: str
    sha: str
    repo: Dict[str, Any]

class PullRequestInfo(BaseModel):
    title: str
    state: str
    merged: Optional[bool] = False
    merged_by: Optional[UserInfo] = None
    user: UserInfo
    head: BranchInfo
    base: BranchInfo
    html_url: str
    number: int
    id: int

class IssueInfo(BaseModel):
    title: str
    state: str
    user: UserInfo
    html_url: str
    number: int
    id: int

class ReviewInfo(BaseModel):
    state: str
    user: UserInfo
    body: Optional[str] = None
    submitted_at: str
    id: int

class CommentInfo(BaseModel):
    body: str
    user: UserInfo
    html_url: str
    id: int

class WorkflowInfo(BaseModel):
    name: str
    status: str
    actor: str
    run_number: int
    run_id: int

# Main GitHub Webhook Model
class GitHubWebhook(BaseModel):
    repository: RepositoryInfo
    ref: Optional[str] = None
    ref_type: Optional[str] = None
    sender: Optional[UserInfo] = None
    
    workflow: Optional[WorkflowInfo] = None
    action: Optional[str] = None

    # Event-specific fields
    pusher: Optional[PusherInfo] = None
    commits: Optional[List[CommitInfo]] = []
    head_commit: Optional[CommitInfo] = None

    pull_request: Optional[PullRequestInfo] = None
    issue: Optional[IssueInfo] = None
    pull_request_review: Optional[ReviewInfo] = None
    comment: Optional[CommentInfo] = None

# Telegram bot class to send messages
class TelegramBot:
    def __init__(self):
        self.bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        if not self.bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN is required")

        self.api_url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"

    async def send_message(self, chat_id: str, message: str):
        async with httpx.AsyncClient() as client:
            response = await client.post(self.api_url, json={
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True
            })
            if response.status_code != 200:
                logging.error(f"Failed to send message to {chat_id}. Response: {response.text}")
                raise HTTPException(status_code=500, detail="Failed to send Telegram message")

bot = TelegramBot()

async def github_repo_exists(repo_name: str) -> bool:
    """Checks if the given GitHub repository exists with authentication"""
    github_api_url = f"https://api.github.com/repos/{repo_name}"
    github_token = os.getenv("GITHUB_TOKEN")
    
    logging.info(f"GITHUB_TOKEN is set: {bool(github_token)}")

    headers = {}
    if github_token:
        headers["Authorization"] = f"token {github_token}"

    async with httpx.AsyncClient() as client:
        response = await client.get(github_api_url, headers=headers)

    logging.info(f"Checked GitHub repo: {repo_name}, Status: {response.status_code}")
    
    return response.status_code == 200

# Dependency to get database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Store user states and temporary data for Telegram onboarding
USER_STATES = {}
USER_DATA = {}

@app.post("/telegram_webhook")
async def telegram_webhook(request: Request, db: Session = Depends(get_db)):
    """Handles incoming Telegram messages and guides user setup"""
    data = await request.json()
    
    if "message" not in data:
        return {"status": "ignored"}

    chat_id = str(data["message"]["chat"]["id"])
    text = data["message"].get("text", "").strip()

    if chat_id not in USER_STATES:
        USER_STATES[chat_id] = "start"
        USER_DATA[chat_id] = {"chat_id": chat_id}

    state = USER_STATES[chat_id]

    logging.info(f"Received message: {text} from chat_id: {chat_id} (State: {state})")

    # Start trigger
    if text in ["/start", "Hi", "Hello"]:
        USER_STATES[chat_id] = "waiting_for_repo"
        return await bot.send_message(chat_id, "Welcome to *GitHub Notifications Bot*!\n\nEnter your GitHub repository in the format: `username/repository_name`.\n\nExample: `username/awesome-project`")

    elif state == "waiting_for_repo":
        repo_name = text
        if not re.match(r"^[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+$", repo_name):
            return await bot.send_message(chat_id, "❌ Invalid format! Enter your repository as `username/repository_name`.\nExample: `username/awesome-project`")
            
        if not await github_repo_exists(repo_name):
            return await bot.send_message(chat_id, "❌ Repository not found! Check the repository name and try again.")
            
        USER_DATA[chat_id]["github_repo"] = repo_name
        USER_STATES[chat_id] = "waiting_for_api_key"
        return await bot.send_message(chat_id, "Great! Now, enter your API Key or type 'none' to generate one.")

    elif state == "waiting_for_api_key":
        if text.lower() == "none":
            # Generate a new API key
            api_key = os.urandom(16).hex()
            USER_DATA[chat_id]["api_key"] = api_key
    
            # Save new integration to the database
            new_integration = Integration(
                github_repo=USER_DATA[chat_id]["github_repo"],
                chat_id=chat_id,
                api_key=api_key
            )
            db.add(new_integration)
            db.commit()
            
            # Send confirmation message
            integration_message = (
                f"✅ *GitHub Integration Complete!*\n\n"
                f"Your repository `{USER_DATA[chat_id]['github_repo']}` is now connected.\n"
                f"*Webhook URL:* `https://your-domain.com/notifications/github`\n"
                f"*API Key:* `{USER_DATA[chat_id]['api_key']}`\n\n"
                f"🔹 *Setup Instructions:*\n"
                f"1. Go to your repository's settings on GitHub.\n"
                f"2. Navigate to *Webhooks* > *Add webhook*.\n"
                f"3. Use the URL above as the *Payload URL*.\n"
                f"4. Choose `application/json` as content type.\n"
                f"5. Set your secret to `{api_key}`.\n"
                f"6. Click *Add webhook*."
            )
            await bot.send_message(chat_id, integration_message)
        else:
            api_key = text
    
            # Validate API key against database
            integration = db.query(Integration).filter(
                Integration.github_repo == USER_DATA[chat_id]["github_repo"],
                Integration.api_key == api_key
            ).first()
    
            if not integration:
                return await bot.send_message(
                    chat_id, 
                    "❌ Invalid API key! Ensure you're entering the correct key linked to your repository.\n"
                    "Try again or type 'none' to generate a new API key."
                )
            
            # API key is valid, store it
            USER_DATA[chat_id]["api_key"] = api_key
                
            integration_message = (
                f"🔹 *Follow The Instructions To Setup in GitHub:*\n\n"
                f"1. Go to your repository's settings on GitHub.\n"
                f"2. Navigate to *Webhooks* > *Add webhook*.\n"
                f"3. Use the URL: `https://your-domain.com/notifications/github` as the *Payload URL*.\n"
                f"4. Choose `application/json` as content type.\n"
                f"5. Set your secret to `{api_key}`.\n"
                f"6. Click *Add webhook*."
            )
    
            await bot.send_message(
                chat_id, 
                "✅ Your API key is valid!\n\n"
                "Follow the steps below to set up your webhook in GitHub."
            )
            
            await bot.send_message(chat_id, integration_message)

        # Cleanup user data
        del USER_STATES[chat_id]
        del USER_DATA[chat_id]

        return await bot.send_message(chat_id, "✅ Integration complete! You will now receive GitHub notifications here.")

    return {"status": "ok"}

async def verify_github_signature(request: Request, api_key: str, received_signature: str):
    """Verifies GitHub webhook signature by hashing API key and comparing it"""
    
    if not received_signature or not api_key:
        raise HTTPException(status_code=401, detail="Missing Webhook Secret or Signature")

    payload = await request.body()
    expected_signature = hmac.new(
        api_key.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected_signature, received_signature):
        raise HTTPException(status_code=401, detail="Signature verification failed")

@app.post("/notifications/github")
async def handle_github_webhook(
    request: Request,
    db: Session = Depends(get_db)
):
    """Handles GitHub webhook notifications"""
    # Extract event type from headers
    event_type = request.headers.get("X-GitHub-Event", "").lower()
    received_signature = request.headers.get("X-Hub-Signature-256", "").replace("sha256=", "").strip()

    try:
        data = await request.json()
        logging.info(f"Received {event_type} event")
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    # Allow "ping" event through without authentication
    if event_type == "ping":
        return {"status": "ok", "message": "Ping received successfully"}

    # Extract repository name from the webhook payload
    try:
        repo_name = data["repository"]["full_name"].lower()
    except KeyError:
        raise HTTPException(status_code=400, detail="Missing repository information")

    # Fetch integration details using repo name
    integration = db.query(Integration).filter(
        func.lower(Integration.github_repo) == repo_name.lower()
    ).first()
    
    if not integration:
        logging.warning(f"No matching integration found for repo: {repo_name}")
        raise HTTPException(status_code=403, detail="No matching integration found for repository")

    # Extract API key from the integration entry
    api_key = integration.api_key

    # Verify GitHub signature using the stored API key
    await verify_github_signature(request, api_key, received_signature)

    # Parse webhook payload
    try:
        webhook = GitHubWebhook(**data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid payload format: {str(e)}")

    # Format message for Telegram based on event type
    if event_type == "push":
        pusher = webhook.pusher.name if webhook.pusher else "Unknown"
        message = (
            f"🔔 *GitHub Push Update*\n\n"
            f"*Repository:* `{webhook.repository.full_name}`\n"
            f"*Branch:* `{webhook.ref}`\n"
            f"*Pusher:* `{pusher}`\n"
            f"*Commits:* {len(webhook.commits)} new commit(s)\n"
            f"*Head Commit:* `{webhook.head_commit.message}`\n"
            f"*Timestamp:* `{webhook.head_commit.timestamp}`\n"
            f"[View Commits](https://github.com/{webhook.repository.full_name}/commits/{webhook.ref})"
        )
    elif event_type == "workflow_run":
        message = (
            f"🔔 *GitHub Workflow Update*\n\n"
            f"*Repository:* `{webhook.repository.full_name}`\n"
            f"*Workflow:* `{webhook.workflow.name}`\n"
            f"*Status:* `{webhook.workflow.status}`\n"
            f"*Triggered by:* `{webhook.workflow.actor}`\n"
            f"*Run:* #{webhook.workflow.run_number}\n"
            f"*Branch:* `{webhook.ref}`\n"
            f"[View Run](https://github.com/{webhook.repository.full_name}/actions/runs/{webhook.workflow.run_id})"
        )
    elif event_type == "pull_request":
        pr_action = webhook.action
        pr_state = webhook.pull_request.state
        merged = webhook.pull_request.merged
        merger = webhook.pull_request.merged_by.login if merged else None
        
        if pr_action == "closed" and merged:
            message = (
                f"🚀 *Pull Request Merged!*\n\n"
                f"*Repository:* `{webhook.repository.full_name}`\n"
                f"*PR Title:* `{webhook.pull_request.title}`\n"
                f"*Merged by:* `{merger}`\n"
                f"*Source Branch:* `{webhook.pull_request.head.ref}`\n"
                f"*Target Branch:* `{webhook.pull_request.base.ref}`\n"
                f"[View Merge]({webhook.pull_request.html_url})"
            )
        else:
            message = (
                f"🔔 *GitHub Pull Request {pr_action.capitalize()}*\n\n"
                f"*Repository:* `{webhook.repository.full_name}`\n"
                f"*PR Title:* `{webhook.pull_request.title}`\n"
                f"*Author:* `{webhook.pull_request.user.login}`\n"
                f"*State:* `{pr_state}`\n"
                f"*Branch:* `{webhook.pull_request.head.ref}` → `{webhook.pull_request.base.ref}`\n"
                f"[View Pull Request]({webhook.pull_request.html_url})"
            )
    elif event_type == "issues":
        message = (
            f"🔔 *GitHub Issue Update*\n\n"
            f"*Repository:* `{webhook.repository.full_name}`\n"
            f"*Issue Title:* `{webhook.issue.title}`\n"
            f"*Author:* `{webhook.issue.user.login}`\n"
            f"*State:* `{webhook.issue.state}`\n"
            f"[View Issue]({webhook.issue.html_url})"
        )
    elif event_type == "create":
        message = (
            f"🆕 *New {webhook.ref_type.capitalize()} Created*\n\n"
            f"*Repository:* `{webhook.repository.full_name}`\n"
            f"*Ref Type:* `{webhook.ref_type}`\n"
            f"*Ref Name:* `{webhook.ref}`\n"
            f"*Created By:* `{webhook.sender.login}`\n"
            f"[View Repository](https://github.com/{webhook.repository.full_name})"
        )
    elif event_type == "delete":
        message = (
            f"🗑️ *{webhook.ref_type.capitalize()} Deleted*\n\n"
            f"*Repository:* `{webhook.repository.full_name}`\n"
            f"*Ref Type:* `{webhook.ref_type}`\n"
            f"*Ref Name:* `{webhook.ref}`\n"
            f"*Deleted By:* `{webhook.sender.login}`\n"
            f"[View Repository](https://github.com/{webhook.repository.full_name})"
        )
    else:
        message = (
            f"🔔 *GitHub Event Received*\n\n"
            f"*Repository:* `{webhook.repository.full_name}`\n"
            f"*Event Type:* `{event_type}`\n"
            f"[View Repository](https://github.com/{webhook.repository.full_name})"
        )

    await bot.send_message(integration.chat_id, message)

    return {"status": "success", "message": "Notification sent"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=True)