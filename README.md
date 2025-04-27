# GitHub-Telegram Integration Bot

A FastAPI-based application that connects GitHub repositories with Telegram for real-time notifications. Get instant updates about pushes, pull requests, issues, workflows, and more directly in your Telegram chat.

## Features

- 🔔 **Real-time notifications** for GitHub events
- 🔐 **Secure webhooks** with HMAC signature verification
- 🚀 **Easy setup** through a conversational Telegram bot
- 📊 **Rich message formatting** with Markdown support
- 📱 **Multiple repository support** in a single Telegram chat
- 🔄 **Event coverage** for pushes, PRs, issues, workflows, branches, and more

## Supported GitHub Events

- Push events
- Pull request events (open, close, merge)
- Issue events
- Workflow run events
- Branch/tag creation and deletion
- And more!

## Prerequisites

- Python 3.7+
- PostgreSQL database
- Telegram Bot Token (obtainable from [@BotFather](https://t.me/BotFather))
- GitHub repository you want to monitor

## Installation

### 1. Clone the repository
```bash
git clone https://github.com/yourusername/github-telegram-bot.git
cd github-telegram-bot
```

### 2. Set up a virtual environment

```bash
python -m venv venv
source venv/bin/activate # On Windows: venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Set up environment variables

Create a `.env` file in the project root:

```bash
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
DATABASE_URL=postgresql://username:password@localhost/database_name
GITHUB_TOKEN=your_github_personal_access_token # Optional but recommended
```

### 5. Initialize the database


## Deployment

### Option 1: Deploy to Railway

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/new/template?template=https%3A%2F%2Fgithub.com%2Fyourusername%2Fgithub-telegram-bot)

1. Click the button above
2. Add the required environment variables in the Railway dashboard
3. Deploy the application

### Option 2: Run locally

```bash
uvicorn app:app --reload
```

## Setup Instructions

### 1. Set up the Telegram webhook

After deploying your application, register your Telegram bot webhook by visiting:

```bash
https://api.telegram.org/bot{YOUR_TELEGRAM_BOT_TOKEN}/setWebhook?url={YOUR_DEPLOYED_URL}/notifications/telegram
```

Replace `{YOUR_TELEGRAM_BOT_TOKEN}` with your actual bot token and `{YOUR_DEPLOYED_URL}` with your application's URL.

Verify the webhook is set up correctly:
```bash
https://api.telegram.org/bot{YOUR_TELEGRAM_BOT_TOKEN}/getWebhookInfo
```

### 2. Start a chat with your bot

1. Open Telegram and search for your bot by username
2. Start a conversation with `/start`
3. Follow the prompts to connect your GitHub repository
4. The bot will provide instructions to set up the GitHub webhook
5. Use the provided API key as your webhook secret in GitHub

### 3. Set up GitHub webhook

1. Go to your GitHub repository
2. Navigate to Settings > Webhooks > Add webhook
3. Set the Payload URL to `{YOUR_DEPLOYED_URL}/notifications/github`
4. Set Content type to `application/json`
5. Set the Secret to the API key provided by the bot
6. Select the events you want to be notified about (or choose "Send me everything")
7. Click "Add webhook"

## Troubleshooting

### Webhook not receiving events

- Verify your webhook URLs are correct in both Telegram and GitHub
- Check that your server is publicly accessible
- Ensure environment variables are set correctly
- Check application logs for errors

### Bot not responding to messages

- Verify the Telegram webhook is set up correctly
- Ensure your bot token is valid
- Check that your database connection is working

### GitHub events not being processed

- Verify the webhook secret matches the API key
- Check that the events you want are selected in GitHub webhook settings
- Look for error messages in the logs

## Database Schema

The application uses a simple database structure:

| Column      | Type   | Description                          |
|-------------|--------|--------------------------------------|
| id          | INT    | Primary key                          |
| github_repo | STRING | GitHub repository name (user/repo)   |
| chat_id     | STRING | Telegram chat ID                     |
| created_at  | STRING | ISO timestamp of creation            |
| api_key     | STRING | Secret key for webhook verification  |

## API Endpoints

- `POST /notifications/telegram`: Receives webhooks from Telegram
- `POST /notifications/github`: Receives webhooks from GitHub
- `POST /`: Redirects to GitHub webhook handler (if configured)

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.
