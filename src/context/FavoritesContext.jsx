import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { useAuth } from './AuthContext'; // Assuming AuthContext.jsx is in the same directory
import { db } from '../firebase'; // Firebase config
import {
    collection,
    doc,
    getDocs,
    setDoc,
    deleteDoc,
    query,
    where, // Only if needed for specific queries, not for basic get all favorites by UID
} from 'firebase/firestore';

// Create the favorites context
const FavoritesContext = createContext();

// Custom hook for consuming the context
export const useFavorites = () => {
    const context = useContext(FavoritesContext);
    if (!context) {
        throw new Error('useFavorites must be used within a FavoritesProvider');
    }
    return context;
};

// Provider component
export const FavoritesProvider = ({ children }) => {
    const { currentUser } = useAuth();
    const [favoriteTeams, setFavoriteTeams] = useState([]);
    const [loadingFavorites, setLoadingFavorites] = useState(true); // To track loading state
    const [showOnlyFavorites, setShowOnlyFavorites] = useState(false);

    // Function to get the path to the user's favorites collection
    const getFavoritesCollectionRef = useCallback(() => {
        if (!currentUser) return null;
        return collection(db, 'users', currentUser.uid, 'favorites');
    }, [currentUser]);

    // Load favorites from Firestore when currentUser changes
    useEffect(() => {
        if (currentUser) {
            setLoadingFavorites(true);
            const favoritesColRef = getFavoritesCollectionRef();
            if (!favoritesColRef) { // Should not happen if currentUser is set, but good check
                setFavoriteTeams([]);
                setLoadingFavorites(false);
                return;
            }

            getDocs(favoritesColRef)
                .then((querySnapshot) => {
                    const userFavorites = [];
                    querySnapshot.forEach((doc) => {
                        // Assuming the document ID is the teamId and the document data is the team object
                        userFavorites.push({ id: doc.id, ...doc.data() });
                    });
                    setFavoriteTeams(userFavorites);
                })
                .catch((error) => {
                    console.error('Error fetching favorite teams:', error);
                    setFavoriteTeams([]); // Reset on error
                })
                .finally(() => {
                    setLoadingFavorites(false);
                });
        } else {
            // No user, clear favorites and stop loading
            setFavoriteTeams([]);
            setLoadingFavorites(false);
        }
    }, [currentUser, getFavoritesCollectionRef]);
    
    // toggleFavorite function
    const toggleFavorite = async (team) => {
        if (!currentUser) {
            console.log('User not logged in. Cannot modify favorites.');
            // Optionally, trigger a UI notification or login prompt here
            return;
        }

        if (!team || !team.id) {
            console.error('Invalid team object passed to toggleFavorite');
            return;
        }

        const favoritesColRef = getFavoritesCollectionRef();
        if (!favoritesColRef) return; // Should not happen

        const teamDocRef = doc(favoritesColRef, String(team.id)); // Ensure team.id is a string for doc path

        const isCurrentlyFavorite = favoriteTeams.some(fav => fav.id === team.id);

        try {
            if (isCurrentlyFavorite) {
                // Remove from favorites
                await deleteDoc(teamDocRef);
                setFavoriteTeams(prevFavorites => prevFavorites.filter(fav => fav.id !== team.id));
            } else {
                // Add to favorites
                // We store the whole team object. Make sure it's clean (no undefined, etc.)
                // Firestore can't store undefined values directly.
                // Create a copy of the team object to ensure it's clean
                const teamDataToSave = { ...team }; 
                // Example: remove any problematic fields if necessary before saving
                // delete teamDataToSave.someProblematicField; 

                await setDoc(teamDocRef, teamDataToSave);
                setFavoriteTeams(prevFavorites => [...prevFavorites, teamDataToSave]);
            }
        } catch (error) {
            console.error('Error toggling favorite:', error);
            // Handle error (e.g., show notification)
        }
    };

    const isFavorite = (teamId) => {
        return favoriteTeams.some(team => team.id === teamId);
    };

    const toggleShowOnlyFavorites = () => {
        setShowOnlyFavorites(prev => !prev);
    };
    
    const value = {
        favoriteTeams,
        loadingFavorites, // Expose loading state for UI
        showOnlyFavorites,
        toggleFavorite,
        isFavorite,
        toggleShowOnlyFavorites,
        setShowOnlyFavorites,
        // addFavorite and removeFavorite are effectively replaced by toggleFavorite
        // but can be kept if direct add/remove is needed elsewhere,
        // though they would also need to be updated for Firestore.
    };

    return (
        <FavoritesContext.Provider value={value}>
            {children}
        </FavoritesContext.Provider>
    );
};