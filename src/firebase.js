// Import the functions you need from the SDKs you need
import { initializeApp } from "firebase/app";
import { getFirestore } from "firebase/firestore";
import { getAnalytics } from "firebase/analytics";
import { getAuth } from "firebase/auth";

// Your web app's Firebase configuration
const firebaseConfig = {
    apiKey: "AIzaSyDncOm08locgxANdkL6JZpp1kSTm-5gGxs",
    authDomain: "hockey-tracker-e67d0.firebaseapp.com",
    projectId: "hockey-tracker-e67d0",
    storageBucket: "hockey-tracker-e67d0.firebasestorage.app",
    messagingSenderId: "78172159693",
    appId: "1:78172159693:web:967172bca6b18c5f787384",
    measurementId: "G-4JLGV7PR5J"
};

// Initialize Firebase
const app = initializeApp(firebaseConfig);
const db = getFirestore(app);
const analytics = getAnalytics(app);
const auth = getAuth(app); // Add this line

export { db, analytics, auth }; // Add auth here
export default app;