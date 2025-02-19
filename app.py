from fastapi import FastAPI, HTTPException, Depends, Security
    # Generate unique API key
    api_key = os.urandom(16).hex()
    
    # Create new integration
    integration = Integration(
        github_repo=request.github_repo,
        telegram_chat_id=request.telegram_chat_id,
        api_key=api_key
    )
    
    db.add(integration)
    db.commit()
    
    # Send test message to Telegram
    welcome_message = (
        f"🔗 *GitHub Integration Setup Complete*\n\n"
        f"Your GitHub repository `{request.github_repo}` has been connected to this chat.\n"
        f"You will receive notifications for workflow runs here.\n\n"
        f"Your API Key: `{api_key}`\n"
        f"Add this key to your GitHub repository secrets as `API_TOKEN`"
    )
    
    await bot.send_message(request.telegram_chat_id, welcome_message)
    
    return {
        "status": "success",
        "api_key": api_key,
        "message": "Integration setup complete. Add the API key to your GitHub repository secrets."
    }

@app.post("/notifications/github")
async def handle_github_webhook(
    webhook: GitHubWebhook,
    credentials: HTTPAuthorizationCredentials = Security(security),
    db: Session = Depends(get_db)
):
    # Find integration by API key
    integration = db.query(Integration).filter_by(api_key=credentials.credentials).first()
    if not integration:
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    # Verify repository matches
    if integration.github_repo != webhook.repository:
        raise HTTPException(status_code=403, detail="Repository mismatch")
    
    # Format message
    message = (
        f"🔔 *GitHub Workflow Update*\n\n"
        f"*Repository:* `{webhook.repository}`\n"
        f"*Workflow:* `{webhook.workflow}`\n"
        f"*Status:* `{webhook.status}`\n"
        f"*Triggered by:* `{webhook.actor}`\n"
        f"*Run:* #{webhook.run_number}\n"
        f"*Branch:* `{webhook.ref}`\n\n"
        f"[View Run](https://github.com/{webhook.repository}/actions/runs/{webhook.run_id})"
    )
    
    # Send to Telegram
    await bot.send_message(integration.telegram_chat_id, message)
    
    return {"status": "success", "message": "Notification sent"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
