# Mentone Hockey Club Dashboard

This project is a web application designed to serve as a comprehensive dashboard for the Mentone Hockey Club. It provides easy access to information about teams, upcoming games, match results, player statistics, ladder positions, and tools for travel planning and venue management.

The application is built with a modern JavaScript frontend and a Python backend powered by FastAPI for data acquisition and processing.

## Project Structure

The project is organized into two main parts:

*   **Frontend (`src/`):** A React application built with Vite and styled with Tailwind CSS. It interacts with Firebase services to fetch and display data. More details can be found in [`src/README.md`](./src/README.md).
*   **Backend (`backend/`):**
    *   The `backend/` directory contains a FastAPI application. It reuses the existing scraping logic to populate Firestore and exposes HTTP endpoints that can be deployed as a container.

## Key Features

*   View upcoming games and schedules.
*   Browse teams and detailed team information.
*   Track team performance and ladder standings.
*   Access player statistics.
*   Get weekly summaries of club activities.
*   Plan travel to game venues.
*   Manage venue information.

## Technologies Used

*   **Frontend:** React, Vite, JavaScript, Tailwind CSS, Firebase (Authentication, Firestore)
*   **Backend:** Python, FastAPI, Firebase (Firestore)
*   **Deployment:** Firebase Hosting (frontend), containerized FastAPI app for backend APIs

## Getting Started

To get started with development, please refer to the README files in the `src/` directory for the frontend and the `backend/` directory for the FastAPI service.

### Backend Development

To run the FastAPI backend locally:
```bash
pip install -r backend/requirements.txt
uvicorn backend.app:app --reload
```
You can build a container for deployment using:
```bash
docker build -t mentone-hockey .
```

