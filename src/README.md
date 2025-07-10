# Mentone Hockey Club Dashboard - Frontend

This directory contains the frontend code for the Mentone Hockey Club Dashboard, built using React, Vite, and Tailwind CSS. It interfaces with Firebase for data display and user interactions.

## Technologies Used

*   **React:** A JavaScript library for building user interfaces.
*   **Vite:** A fast build tool and development server for modern web projects.
*   **Tailwind CSS:** A utility-first CSS framework for rapid UI development.
*   **React Router:** For client-side routing and navigation within the application.
*   **Firebase:** Utilized for fetching data (Firestore) that is populated by the backend services.
*   **Axios:** For making HTTP requests to backend APIs (if any beyond Firebase direct access).
*   **Recharts:** For displaying charts and graphs (e.g., team performance).

## Project Structure Overview

*   **`main.jsx`:** The entry point of the application.
*   **`App.jsx`:** The root component that sets up routing.
*   **`components/`:** Contains reusable UI components used throughout the application (e.g., `Navbar.jsx`, `UpcomingGames.jsx`, `TeamList.jsx`).
*   **`firebase.js`:** Firebase configuration and initialization.
*   **`assets/`:** Static assets like images and icons.
*   **`styles/`:** Global styles and Tailwind CSS configuration.

## Prerequisites

*   **Node.js:** (Version 18.x or later recommended) - Download from [nodejs.org](https://nodejs.org/)
*   **npm** (Node Package Manager) or **yarn**: These come bundled with Node.js or can be installed separately.

## Getting Started

1.  **Clone the repository (if you haven't already):**
    ```bash
    git clone <repository-url>
    cd <repository-name>
    ```

2.  **Navigate to the project root directory.** The frontend is part of a larger project, so these commands should be run from the root.

3.  **Install dependencies:**
    Open your terminal in the root directory of the project and run:
    ```bash
    npm install
    # OR
    # yarn install
    ```

4.  **Firebase Configuration:**
    The application connects to Firebase services. Ensure you have the necessary Firebase configuration:
    *   The Firebase configuration is typically initialized in `src/firebase.js`.
    *   For local development, this configuration should allow connecting to your Firebase project. Ensure your Firebase project has Firestore enabled and appropriate security rules.
    *   If running against a live Firebase project, ensure your local environment is authorized or the rules permit access from `localhost` during development if necessary.

5.  **Run the development server:**
    ```bash
    npm run dev
    # OR
    # yarn dev
    ```
    This will start the Vite development server, typically at `http://localhost:5173`. The application will automatically reload if you make changes to the code.

## Available Scripts

In the project's root directory, you can run the following scripts (as defined in `package.json`):

*   `npm run dev` or `yarn dev`: Starts the development server.
*   `npm run build` or `yarn build`: Bundles the app into static files for production in the `dist` folder.
*   `npm run lint` or `yarn lint`: Lints the JavaScript and JSX files for code quality and errors.
*   `npm run preview` or `yarn preview`: Serves the production build locally to preview it.

## Building for Production

To create a production build of the app, run:

```bash
npm run build
# OR
# yarn build
```

This command will generate a `dist` folder in the project root with the optimized static assets for your application. These files can then be deployed to a static site hosting service like Firebase Hosting.
