import { useState, useEffect } from "react";
import { collection, query, where, orderBy, limit, getDocs } from "firebase/firestore";
import { db } from "../firebase";

const UpcomingGames = () => {
    const [games, setGames] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [dateFilter, setDateFilter] = useState("thisWeek"); // options: thisWeek, nextWeek, twoWeeks

    useEffect(() => {
        fetchUpcomingGames(dateFilter);
    }, [dateFilter]);

    const fetchUpcomingGames = async (filter) => {
        try {
            setLoading(true);

            // Get current date at midnight
            const now = new Date();
            now.setHours(0, 0, 0, 0);

            // Calculate end date based on filter
            const endDate = new Date(now);
            if (filter === "thisWeek") {
                endDate.setDate(now.getDate() + 7);
            } else if (filter === "nextWeek") {
                now.setDate(now.getDate() + 7); // Start from next week
                endDate.setDate(now.getDate() + 7);
            } else if (filter === "twoWeeks") {
                endDate.setDate(now.getDate() + 14);
            }

            const gamesQuery = query(
                collection(db, "games"),
                where("date", ">=", now),
                where("date", "<=", endDate),
                orderBy("date", "asc"),
                limit(20)
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

    // Group games by date for better organization
    const groupGamesByDate = () => {
        const grouped = {};

        games.forEach(game => {
            const gameDate = game.date?.toDate ? game.date.toDate() : new Date(game.date);
            const dateStr = gameDate.toLocaleDateString("en-AU", {
                weekday: 'long',
                day: 'numeric',
                month: 'short'
            });

            if (!grouped[dateStr]) {
                grouped[dateStr] = [];
            }

            grouped[dateStr].push(game);
        });

        return grouped;
    };

    if (loading) {
        return <div className="text-center p-4">Loading upcoming games...</div>;
    }

    if (error) {
        return <div className="text-red-600 p-4">Error: {error}</div>;
    }

    const groupedGames = groupGamesByDate();

    return (
        <div className="p-4 bg-white rounded-lg shadow">
            <div className="flex justify-between items-center mb-6">
                <h2 className="text-2xl font-bold text-mentone-navy">Upcoming Games</h2>

                <div className="flex space-x-2">
                    <button
                        onClick={() => setDateFilter("thisWeek")}
                        className={`px-3 py-2 text-sm rounded-md transition-colors ${
                            dateFilter === "thisWeek"
                                ? "bg-mentone-navy text-white"
                                : "bg-gray-200 hover:bg-gray-300 text-gray-700"
                        }`}
                    >
                        This Week
                    </button>
                    <button
                        onClick={() => setDateFilter("nextWeek")}
                        className={`px-3 py-2 text-sm rounded-md transition-colors ${
                            dateFilter === "nextWeek"
                                ? "bg-mentone-navy text-white"
                                : "bg-gray-200 hover:bg-gray-300 text-gray-700"
                        }`}
                    >
                        Next Week
                    </button>
                    <button
                        onClick={() => setDateFilter("twoWeeks")}
                        className={`px-3 py-2 text-sm rounded-md transition-colors ${
                            dateFilter === "twoWeeks"
                                ? "bg-mentone-navy text-white"
                                : "bg-gray-200 hover:bg-gray-300 text-gray-700"
                        }`}
                    >
                        Two Weeks
                    </button>
                </div>
            </div>

            {games.length === 0 ? (
                <div className="text-center p-6 bg-gray-50 rounded-lg border border-gray-200">
                    <p className="text-gray-600">No upcoming games scheduled for this period</p>
                </div>
            ) : (
                <div className="space-y-8">
                    {Object.entries(groupedGames).map(([date, dateGames]) => (
                        <div key={date} className="space-y-4">
                            <h3 className="text-lg font-semibold text-mentone-navy border-b border-gray-200 pb-2">
                                {date}
                            </h3>

                            <div className="space-y-4">
                                {dateGames.map((game) => (
                                    <div
                                        key={game.id}
                                        className="bg-white rounded-lg border border-gray-200 overflow-hidden hover:shadow-md transition-shadow"
                                    >
                                        <div className="p-4">
                                            <div className="flex justify-between items-center mb-2">
                                                <div className="flex items-center">
                                                    <span className="font-medium text-gray-700">
                                                        {game.date?.toDate ? game.date.toDate().toLocaleTimeString('en-AU', {
                                                            hour: '2-digit',
                                                            minute: '2-digit',
                                                            hour12: true
                                                        }) : "Time TBD"}
                                                    </span>
                                                </div>
                                                <span className="text-sm bg-mentone-skyblue bg-opacity-20 text-mentone-navy px-3 py-1 rounded-full">
                                                    Round {game.round || "?"}
                                                </span>
                                            </div>

                                            <div className="flex items-center justify-between my-3">
                                                {/* Home Team */}
                                                <div className="flex flex-col items-start max-w-[40%]">
                                                    <span className={`text-lg font-bold truncate w-full ${
                                                        game.home_team?.club === "Mentone"
                                                            ? "text-mentone-navy"
                                                            : "text-gray-700"
                                                    }`}>
                                                        {game.home_team?.name || "TBD"}
                                                    </span>
                                                    {game.home_team?.club === "Mentone" && game.home_team?.type && (
                                                        <span className="text-xs text-mentone-skyblue font-medium">
                                                            {game.home_team.type} - {game.home_team.gender}
                                                        </span>
                                                    )}
                                                </div>

                                                {/* VS */}
                                                <div className="flex items-center mx-2">
                                                    <span className="text-gray-400 text-sm font-medium">vs</span>
                                                </div>

                                                {/* Away Team */}
                                                <div className="flex flex-col items-end max-w-[40%]">
                                                    <span className={`text-lg font-bold truncate w-full text-right ${
                                                        game.away_team?.club === "Mentone"
                                                            ? "text-mentone-navy"
                                                            : "text-gray-700"
                                                    }`}>
                                                        {game.away_team?.name || "TBD"}
                                                    </span>
                                                    {game.away_team?.club === "Mentone" && game.away_team?.type && (
                                                        <span className="text-xs text-mentone-skyblue font-medium">
                                                            {game.away_team.type} - {game.away_team.gender}
                                                        </span>
                                                    )}
                                                </div>
                                            </div>

                                            <div className="mt-3 text-sm text-gray-600">
                                                <div className="flex items-center">
                                                    <svg
                                                        xmlns="http://www.w3.org/2000/svg"
                                                        className="h-4 w-4 mr-1 text-gray-500"
                                                        viewBox="0 0 20 20"
                                                        fill="currentColor"
                                                    >
                                                        <path fillRule="evenodd" d="M5.05 4.05a7 7 0 119.9 9.9L10 18.9l-4.95-4.95a7 7 0 010-9.9zM10 11a2 2 0 100-4 2 2 0 000 4z" clipRule="evenodd" />
                                                    </svg>
                                                    <span className="truncate">
                                                        {game.venue || "Venue TBD"}
                                                    </span>
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
};

export default UpcomingGames;