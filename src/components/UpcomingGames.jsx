import { useState, useEffect } from "react";
import { collection, query, where, orderBy, limit, getDocs } from "firebase/firestore";
import { db } from "../firebase";

const UpcomingGames = () => {
    const [games, setGames] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    useEffect(() => {
        const fetchUpcomingGames = async () => {
            try {
                setLoading(true);

                // Get current date
                const now = new Date();

                // Create query for upcoming games in the next 7 days
                const nextWeek = new Date();
                nextWeek.setDate(now.getDate() + 7);

                const gamesQuery = query(
                    collection(db, "games"),
                    where("date", ">=", now),
                    where("date", "<=", nextWeek),
                    orderBy("date", "asc"),
                    limit(10)
                );

                const querySnapshot = await getDocs(gamesQuery);
                const gamesData = querySnapshot.docs.map(doc => ({
                    id: doc.id,
                    ...doc.data()
                }));

                setGames(gamesData);
                setLoading(false);
            } catch (err) {
                console.error("Error fetching upcoming games:", err);
                setError(err.message);
                setLoading(false);
            }
        };

        fetchUpcomingGames();
    }, []);

    // Format date nicely
    const formatGameDate = (date) => {
        if (!date) return "TBD";

        // Handle Firestore Timestamp objects and convert to JS Date
        const gameDate = date.toDate ? date.toDate() : new Date(date);

        return gameDate.toLocaleDateString("en-AU", {
            weekday: 'short',
            day: 'numeric',
            month: 'short',
            hour: '2-digit',
            minute: '2-digit'
        });
    };

    if (loading) {
        return <div className="text-center p-4">Loading upcoming games...</div>;
    }

    if (error) {
        return <div className="text-red-600 p-4">Error: {error}</div>;
    }

    return (
        <div className="p-4">
            <h2 className="text-2xl font-bold text-blue-600 mb-6">This Week's Games</h2>

            {games.length === 0 ? (
                <div className="text-center p-4 bg-gray-100 rounded-lg">
                    No upcoming games scheduled for this week
                </div>
            ) : (
                <div className="space-y-4">
                    {games.map((game) => (
                        <div
                            key={game.id}
                            className="bg-white rounded-lg shadow-md overflow-hidden border border-gray-200"
                        >
                            <div className="p-4">
                                <div className="flex justify-between items-center mb-3">
                                    <span className="font-medium text-gray-600">{formatGameDate(game.date)}</span>
                                    <span className="text-sm bg-gray-200 px-2 py-1 rounded">Round {game.round || "?"}</span>
                                </div>

                                <div className="flex items-center justify-between">
                                    <div className="flex flex-col items-start">
                    <span className={`text-lg font-bold ${game.home_team.club === "Mentone" ? "text-blue-600" : ""}`}>
                      {game.home_team.name}
                    </span>
                                    </div>

                                    <div className="flex items-center">
                                        <span className="mx-2 text-gray-400">vs</span>
                                    </div>

                                    <div className="flex flex-col items-end">
                    <span className={`text-lg font-bold ${game.away_team.club === "Mentone" ? "text-blue-600" : ""}`}>
                      {game.away_team.name}
                    </span>
                                    </div>
                                </div>

                                <div className="mt-3 text-sm text-gray-600">
                                    <div className="flex items-center">
                                        <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
                                        </svg>
                                        {game.venue || "Venue TBD"}
                                    </div>
                                </div>
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
};

export default UpcomingGames;