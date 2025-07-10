# Mentone Hockey Club Dashboard

This project is a web application designed to serve as a comprehensive dashboard for the Mentone Hockey Club. It provides easy access to information about teams, upcoming games, match results, player statistics, ladder positions, and tools for travel planning and venue management.

The application is built with a modern JavaScript frontend and a Python backend that handles data acquisition and processing.

## Project Structure

The project is organized into two main parts:

*   **Frontend (`src/`):** A React application built with Vite and styled with Tailwind CSS. It interacts with Firebase services to fetch and display data. More details can be found in [`src/README.md`](./src/README.md).
*   **Backend (`backend/` and `functions/`):**
    *   The `backend/` directory contains Python scripts responsible for scraping data from sources like Hockey Victoria, processing this data, and storing it in Firebase Firestore.
    *   The `functions/` directory contains Firebase Cloud Functions written in Python that provide API endpoints for the frontend application.
    *   More details about the backend setup and operations can be found in [`backend/README.md`](./backend/README.md).

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
*   **Backend:** Python, Firebase (Firestore, Cloud Functions)
*   **Deployment:** Firebase Hosting (frontend), Firebase Cloud Functions (backend APIs)

## Getting Started

To get started with development, please refer to the README files in the respective `src/` (for frontend) and `backend/` directories.
