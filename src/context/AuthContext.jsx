import { createContext, useContext, useEffect, useState } from 'react';
import {
    onAuthStateChanged,
    GoogleAuthProvider,
    signInWithPopup,
    signOut,
    // signInWithEmailAndPassword, // Add if email/password login is implemented
    // createUserWithEmailAndPassword, // Add if email/password signup is implemented
} from 'firebase/auth';
import { auth } from '../firebase'; // Ensure this path is correct

const AuthContext = createContext();

export const AuthProvider = ({ children }) => {
    const [currentUser, setCurrentUser] = useState(null);
    const [loading, setLoading] = useState(true);

    const loginWithGoogle = async () => {
        const provider = new GoogleAuthProvider();
        try {
            await signInWithPopup(auth, provider);
            // User will be set by onAuthStateChanged
        } catch (error) {
            console.error("Error signing in with Google:", error);
            // Handle error (e.g., show a notification to the user)
        }
    };

    // Placeholder for email/password login
    // const loginWithEmail = async (email, password) => {
    //     try {
    //         await signInWithEmailAndPassword(auth, email, password);
    //     } catch (error) {
    //         console.error("Error signing in with email:", error);
    //     }
    // };

    const logout = async () => {
        try {
            await signOut(auth);
        } catch (error) {
            console.error("Error signing out:", error);
        }
    };

    useEffect(() => {
        const unsubscribe = onAuthStateChanged(auth, (user) => {
            setCurrentUser(user);
            setLoading(false);
        });

        // Cleanup subscription on unmount
        return () => unsubscribe();
    }, []);

    const value = {
        currentUser,
        loading,
        loginWithGoogle,
        // loginWithEmail, // Add if implementing
        logout,
    };

    return (
        <AuthContext.Provider value={value}>
            {!loading && children}
        </AuthContext.Provider>
    );
};

export const useAuth = () => {
    return useContext(AuthContext);
};
