#!/bin/bash

echo "🔄 Setting up hockey-app..."

# Check if account is authenticated
ACCOUNT="steve.g.waters@gmail.com"
PROJECT="hockey-tracker-e67d0"
if ! gcloud auth list --filter="account:$ACCOUNT" --format="value(account)" | grep -q "$ACCOUNT"; then
    echo "🔐 Logging in $ACCOUNT..."
    gcloud auth login "$ACCOUNT"
    gcloud auth application-default login
fi

# Set project and account
gcloud config set project "hockey-tracker-e67d0"
gcloud config set account "steve.g.waters@gmail.com"

# Export environment variables
export GOOGLE_CLOUD_PROJECT="$PROJECT"

echo "✅ Mentone ready: $PROJECT ($ACCOUNT)"