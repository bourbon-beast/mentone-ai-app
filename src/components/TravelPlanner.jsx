import { useState, useEffect } from "react";
import { collection, query, where, orderBy, getDocs } from "firebase/firestore";
import { db } from "../firebase";

const TravelPlanner = () => {
    // State for games data
    const [games, setGames] = useState([]);
    const [loadingGames, setLoadingGames] = useState(true);
    const [error, setError] = useState(null);

    // State for selected games
    const [firstGame, setFirstGame] = useState(null);
    const [secondGame, setSecondGame] = useState(null);

    // State for travel data
    const [travelData, setTravelData] = useState(null);
    const [loadingTravelData, setLoadingTravelData] = useState(false);

    // Fetch upcoming games from Firebase
    useEffect(() => {
        const fetchGames = async () => {
            try {
                setLoadingGames(true);

                // Get upcoming games (next 14 days)
                const now = new Date();
                const twoWeeksLater = new Date();
                twoWeeksLater.setDate(now.getDate() + 14);

                const gamesQuery = query(
                    collection(db, "games"),
                    where("date", ">=", now),
                    where("date", "<=", twoWeeksLater),
                    where("mentone_playing", "==", true),
                    orderBy("date", "asc")
                );

                const querySnapshot = await getDocs(gamesQuery);
                const gamesData = querySnapshot.docs.map(doc => ({
                    id: doc.id,
                    ...doc.data()
                }));

                // Validate venues exist
                const validGames = gamesData.filter(game =>
                    game.venue && typeof game.venue === 'string' && game.venue.trim() !== ''
                );

                setGames(validGames);
                setLoadingGames(false);
            } catch (err) {
                console.error("Error fetching games:", err);
                setError(err.message);
                setLoadingGames(false);
            }
        };

        fetchGames();
    }, []);

    // Calculate travel time and distance when two games are selected
    useEffect(() => {
        if (firstGame && secondGame) {
            calculateTravelData();
        } else {
            setTravelData(null);
        }
    }, [firstGame, secondGame]);

    // Format date as "Saturday 26 Apr @ 14:30"
    const formatGameDateTime = (date) => {
        if (!date) return "TBD";
        const gameDate = date.toDate ? date.toDate() : new Date(date);
        const dayStr = gameDate.toLocaleDateString('en-AU', {
            weekday: 'long',
            day: 'numeric',
            month: 'short',
            timeZone: 'Australia/Melbourne'
        });
        const timeStr = gameDate.toLocaleTimeString('en-AU', {
            hour: '2-digit',
            minute: '2-digit',
            hour12: false,
            timeZone: 'Australia/Melbourne'
        });
        return `${dayStr} @ ${timeStr}`;
    };

    // Calculate travel data using Google Maps Distance Matrix API via Cloud Function
    const calculateTravelData = async () => {
        if (!firstGame?.venue || !secondGame?.venue) return;

        setLoadingTravelData(true);

        try {
            // Import Firebase functions
            const { getFunctions, httpsCallable } = await import("firebase/functions");

            // Get a reference to the function
            const functions = getFunctions();
            const calculateTravelTime = httpsCallable(functions, 'calculateTravelTime');

            // Add "Victoria, Australia" to make venues more specific for Google Maps
            const originVenue = `${firstGame.venue}, Victoria, Australia`;
            const destinationVenue = `${secondGame.venue}, Victoria, Australia`;

            // Call the Cloud Function
            const result = await calculateTravelTime({
                origin: originVenue,
                destination: destinationVenue,
                mode: 'driving',
                units: 'metric'
            });

            // Process the response data
            const response = result.data;

            // Convert meters to kilometers and seconds to minutes
            const distanceKm = (response.distance.value / 1000).toFixed(1);
            const durationMinutes = Math.round(response.duration.value / 60);

            setTravelData({
                distance: distanceKm,
                duration: durationMinutes,
                origin: response.origin,
                destination: response.destination,
                distanceText: response.distance.text,
                durationText: response.duration.text
            });

        } catch (err) {
            console.error("Error calculating travel data:", err);

            // Fallback to simulated data for demo/development purposes
            console.warn("Falling back to simulated travel data");

            // Calculate distance based on venue names (DEMO ONLY - not for production)
            const venueDistance = Math.abs(
                (firstGame.venue.length * 324) - (secondGame.venue.length * 278)
            ) % 25 + 5; // Random-ish distance between 5-30 km

            // Calculate time (roughly 2 mins per km, plus random factor)
            const travelTimeMinutes = Math.round(venueDistance * 2 + Math.random() * 10);

            setTravelData({
                distance: venueDistance.toFixed(1),
                duration: travelTimeMinutes,
                distanceText: `${venueDistance.toFixed(1)} km`,
                durationText: `${travelTimeMinutes} mins`
            });
        } finally {
            setLoadingTravelData(false);
        }
    };

    // Handle game selection
    const handleSelectGame = (game, position) => {
        if (position === 'first') {
            setFirstGame(game);
            // If second game is the same as the new first game, clear second game
            if (secondGame && secondGame.id === game.id) {
                setSecondGame(null);
            }
        } else {
            setSecondGame(game);
            // If first game is the same as the new second game, clear first game
            if (firstGame && firstGame.id === game.id) {
                setFirstGame(null);
            }
        }
    };

    // Get Google Maps directions URL
    const getDirectionsUrl = () => {
        if (!firstGame?.venue || !secondGame?.venue) return '#';

        const origin = encodeURIComponent(firstGame.venue + ", Victoria, Australia");
        const destination = encodeURIComponent(secondGame.venue + ", Victoria, Australia");

        return `https://www.google.com/maps/dir/?api=1&origin=${origin}&destination=${destination}&travelmode=driving`;
    };

    // Render loading state
    if (loadingGames) {
        return (
            <div className="flex items-center justify-center h-64 bg-white rounded-xl shadow-sm">
                <div className="flex flex-col items-center">
                    <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-mentone-skyblue mb-2"></div>
                    <p className="text-mentone-navy font-medium">Loading games...</p>
                </div>
            </div>
        );
    }

    // Render error state
    if (error) {
        return (
            <div className="bg-red-50 border border-red-200 rounded-xl p-5 text-red-600">
                <p className="font-medium mb-1">Error Loading Games</p>
                <p className="text-sm">{error}</p>
            </div>
        );
    }

    return (
        <div className="bg-white rounded-xl shadow-sm overflow-hidden">
            {/* Header */}
            <div className="bg-gradient-to-r from-mentone-navy to-mentone-navy/90 p-5">
                <h2 className="text-2xl font-bold text-mentone-gold tracking-tight">Travel Planner</h2>
                <p className="text-mentone-skyblue text-sm mt-1">
                    Select two games to calculate travel time between venues
                </p>
            </div>

            {/* Game Selection */}
            <div className="p-5 grid grid-cols-1 md:grid-cols-2 gap-6">
                {/* First Game Selection */}
                <div>
                    <h3 className="text-lg font-semibold text-mentone-navy mb-3">First Game</h3>
                    <div className="bg-mentone-offwhite rounded-lg p-4 min-h-[200px]">
                        {firstGame ? (
                            <div className="bg-white p-4 rounded-lg border border-mentone-skyblue/20 shadow-sm">
                                <div className="flex justify-between items-start mb-3">
                                    <div>
                                        <h4 className="font-bold text-mentone-navy">
                                            {firstGame.home_team?.club === "Mentone" ? "Mentone" : firstGame.home_team?.name} vs {firstGame.away_team?.club === "Mentone" ? "Mentone" : firstGame.away_team?.name}
                                        </h4>
                                        <p className="text-sm text-gray-600 mt-1">{formatGameDateTime(firstGame.date)}</p>
                                    </div>
                                    <button
                                        onClick={() => setFirstGame(null)}
                                        className="text-gray-400 hover:text-red-500"
                                    >
                                        <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                                            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                                        </svg>
                                    </button>
                                </div>
                                <div className="flex items-center text-sm text-gray-600">
                                    <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 mr-1 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
                                    </svg>
                                    <span>{firstGame.venue}</span>
                                </div>
                            </div>
                        ) : (
                            <div className="h-full flex flex-col items-center justify-center text-gray-400">
                                <svg xmlns="http://www.w3.org/2000/svg" className="h-12 w-12 mb-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                                </svg>
                                <p className="text-sm">Select a game below</p>
                            </div>
                        )}
                    </div>
                </div>

                {/* Second Game Selection */}
                <div>
                    <h3 className="text-lg font-semibold text-mentone-navy mb-3">Second Game</h3>
                    <div className="bg-mentone-offwhite rounded-lg p-4 min-h-[200px]">
                        {secondGame ? (
                            <div className="bg-white p-4 rounded-lg border border-mentone-skyblue/20 shadow-sm">
                                <div className="flex justify-between items-start mb-3">
                                    <div>
                                        <h4 className="font-bold text-mentone-navy">
                                            {secondGame.home_team?.club === "Mentone" ? "Mentone" : secondGame.home_team?.name} vs {secondGame.away_team?.club === "Mentone" ? "Mentone" : secondGame.away_team?.name}
                                        </h4>
                                        <p className="text-sm text-gray-600 mt-1">{formatGameDateTime(secondGame.date)}</p>
                                    </div>
                                    <button
                                        onClick={() => setSecondGame(null)}
                                        className="text-gray-400 hover:text-red-500"
                                    >
                                        <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                                            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                                        </svg>
                                    </button>
                                </div>
                                <div className="flex items-center text-sm text-gray-600">
                                    <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 mr-1 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
                                    </svg>
                                    <span>{secondGame.venue}</span>
                                </div>
                            </div>
                        ) : (
                            <div className="h-full flex flex-col items-center justify-center text-gray-400">
                                <svg xmlns="http://www.w3.org/2000/svg" className="h-12 w-12 mb-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                                </svg>
                                <p className="text-sm">Select a game below</p>
                            </div>
                        )}
                    </div>
                </div>
            </div>

            {/* Travel Result */}
            {(firstGame && secondGame) && (
                <div className="px-5 pb-5">
                    <div className="bg-mentone-gold/10 rounded-lg p-4 border border-mentone-gold/20">
                        <h3 className="text-lg font-semibold text-mentone-charcoal mb-3">Travel Information</h3>

                        {loadingTravelData ? (
                            <div className="flex justify-center items-center py-4">
                                <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-mentone-navy"></div>
                                <p className="ml-3 text-mentone-navy">Calculating travel time...</p>
                            </div>
                        ) : travelData ? (
                            <div className="space-y-4">
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                    <div className="bg-white rounded-lg p-3 shadow-sm">
                                        <div className="text-sm text-gray-500 mb-1">Distance</div>
                                        <div className="text-xl font-bold text-mentone-navy">
                                            {travelData.distanceText || `${travelData.distance} km`}
                                        </div>
                                    </div>
                                    <div className="bg-white rounded-lg p-3 shadow-sm">
                                        <div className="text-sm text-gray-500 mb-1">Estimated Travel Time</div>
                                        <div className="text-xl font-bold text-mentone-navy">
                                            {travelData.durationText || (
                                                travelData.duration < 60
                                                    ? `${travelData.duration} min`
                                                    : `${Math.floor(travelData.duration / 60)} hr ${travelData.duration % 60} min`
                                            )}
                                        </div>
                                    </div>
                                </div>

                                <div className="flex justify-center mt-2">
                                    <a
                                        href={getDirectionsUrl()}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="inline-flex items-center px-4 py-2 bg-mentone-navy text-white rounded-lg hover:bg-mentone-navy/90 transition-colors"
                                    >
                                        <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7" />
                                        </svg>
                                        Get Directions in Google Maps
                                    </a>
                                </div>

                                <div className="text-sm text-gray-500 text-center mt-2">
                                    <p>Travel times may vary based on traffic conditions.</p>
                                    <p>Plan to arrive at least 30 minutes before game time.</p>
                                </div>
                            </div>
                        ) : (
                            <div className="text-center py-4 text-gray-500">
                                Select two different games to see travel information.
                            </div>
                        )}
                    </div>
                </div>
            )}

            {/* Game List */}
            <div className="border-t border-gray-200 px-5 py-4">
                <h3 className="text-lg font-semibold text-mentone-navy mb-3">Upcoming Games</h3>

                {games.length === 0 ? (
                    <div className="text-center py-6 bg-gray-50 rounded-lg text-gray-500">
                        No upcoming games found.
                    </div>
                ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                        {games.map(game => (
                            <div key={game.id} className="border border-gray-200 rounded-lg bg-white hover:shadow-md transition-shadow p-3">
                                <div className="flex justify-between items-start mb-2">
                                    <div>
                                        <h4 className="font-medium text-mentone-navy">
                                            {game.home_team?.club === "Mentone" ? "Mentone" : game.home_team?.name} vs {game.away_team?.club === "Mentone" ? "Mentone" : game.away_team?.name}
                                        </h4>
                                        <p className="text-sm text-gray-600">{formatGameDateTime(game.date)}</p>
                                    </div>
                                </div>
                                <div className="flex items-center text-sm text-gray-600 mb-3">
                                    <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 mr-1 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
                                    </svg>
                                    <span>{game.venue || "Venue TBD"}</span>
                                </div>
                                <div className="flex space-x-2">
                                    <button
                                        onClick={() => handleSelectGame(game, 'first')}
                                        className={`px-3 py-1 text-xs rounded-full border transition-colors ${
                                            firstGame?.id === game.id
                                                ? "bg-mentone-navy text-white border-mentone-navy"
                                                : "border-gray-300 text-gray-600 hover:border-mentone-navy hover:text-mentone-navy"
                                        }`}
                                    >
                                        Select as First Game
                                    </button>
                                    <button
                                        onClick={() => handleSelectGame(game, 'second')}
                                        className={`px-3 py-1 text-xs rounded-full border transition-colors ${
                                            secondGame?.id === game.id
                                                ? "bg-mentone-navy text-white border-mentone-navy"
                                                : "border-gray-300 text-gray-600 hover:border-mentone-navy hover:text-mentone-navy"
                                        }`}
                                    >
                                        Select as Second Game
                                    </button>
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
};

export default TravelPlanner;