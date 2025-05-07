import { createContext, useContext, useState, useEffect } from 'react';

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
    // State to store favorite teams
    const [favoriteTeams, setFavoriteTeams] = useState([]);
    // State to track if we're filtering to show only favorites
    const [showOnlyFavorites, setShowOnlyFavorites] = useState(false);

    // Load favorites from localStorage on component mount
    useEffect(() => {
        const storedFavorites = localStorage.getItem('mentone_favorite_teams');
        if (storedFavorites) {
            try {
                setFavoriteTeams(JSON.parse(storedFavorites));
            } catch (error) {
                console.error('Error parsing stored favorites:', error);
                // If there's an error parsing, reset favorites
                localStorage.removeItem('mentone_favorite_teams');
            }
        }
    }, []);

    // Save favorites to localStorage whenever they change
    useEffect(() => {
        localStorage.setItem('mentone_favorite_teams', JSON.stringify(favoriteTeams));
    }, [favoriteTeams]);

    // Function to add a team to favorites
    const addFavorite = (team) => {
        // Check if team is already in favorites to avoid duplicates
        if (!favoriteTeams.some(fav => fav.id === team.id)) {
            setFavoriteTeams([...favoriteTeams, team]);
        }
    };

    // Function to remove a team from favorites
    const removeFavorite = (teamId) => {
        setFavoriteTeams(favoriteTeams.filter(team => team.id !== teamId));
    };

    // Function to toggle a team's favorite status
    const toggleFavorite = (team) => {
        if (favoriteTeams.some(fav => fav.id === team.id)) {
            removeFavorite(team.id);
        } else {
            addFavorite(team);
        }
    };

    // Function to check if a team is a favorite
    const isFavorite = (teamId) => {
        return favoriteTeams.some(team => team.id === teamId);
    };

    // Toggle the filter to show only favorites
    const toggleShowOnlyFavorites = () => {
        setShowOnlyFavorites(prev => !prev);
    };

    // The context value that will be provided
    const value = {
        favoriteTeams,
        showOnlyFavorites,
        addFavorite,
        removeFavorite,
        toggleFavorite,
        isFavorite,
        toggleShowOnlyFavorites,
        setShowOnlyFavorites
    };

    return (
        <FavoritesContext.Provider value={value}>
            {children}
        </FavoritesContext.Provider>
    );
};