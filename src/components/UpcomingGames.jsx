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

    // Format time only (HH:MM)
    const formatGameTime = (date) => {
        if (!date) return "TBD";
        const gameDate = date.toDate ? date.toDate() : new Date(date);
        return gameDate.toLocaleTimeString('en-AU', {
            hour: '2-digit',
            minute: '2-digit',
            hour12: false
        });
    };

    // Format date only (weekday, day month)
    const formatGameDate = (date) => {
        if (!date) return "TBD";
        const gameDate = date.toDate ? date.toDate() : new Date(date);
        return gameDate.toLocaleDateString('en-AU', {
            weekday: 'long',
            day: 'numeric',
            month: 'short'
        });
    };

    // Group games by date
    const groupGamesByDate = () => {
        const grouped = {};

        games.forEach(game => {
            if (!game.date) return;

            const gameDate = game.date.toDate ? game.date.toDate() : new Date(game.date);
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
        return <div className="text-center p-4 text-white">Loading upcoming games...</div>;
    }

    if (error) {
        return <div className="text-center p-4 text-red-400">Error: {error}</div>;
    }

    const groupedGames = groupGamesByDate();

    return (
        <div className="p-4">
            <div className="flex justify-between items-center mb-6">
                <h2 className="text-2xl font-bold text-white">Upcoming Games</h2>

                <div className="flex space-x-1">
                    <button
                        onClick={() => setDateFilter("thisWeek")}
                        className={`px-3 py-1 text-sm rounded ${
                            dateFilter === "thisWeek"
                                ? "bg-blue-700 text-white"
                                : "bg-gray-700 text-gray-300 hover:bg-gray-600"
                        }`}
                    >
                        This Week
                    </button>
                    <button
                        onClick={() => setDateFilter("nextWeek")}
                        className={`px-3 py-1 text-sm rounded ${
                            dateFilter === "nextWeek"
                                ? "bg-blue-700 text-white"
                                : "bg-gray-700 text-gray-300 hover:bg-gray-600"
                        }`}
                    >
                        Next Week
                    </button>
                    <button
                        onClick={() => setDateFilter("twoWeeks")}
                        className={`px-3 py-1 text-sm rounded ${
                            dateFilter === "twoWeeks"
                                ? "bg-blue-700 text-white"
                                : "bg-gray-700 text-gray-300 hover:bg-gray-600"
                        }`}
                    >
                        Two Weeks
                    </button>
                </div>
            </div>

            {games.length === 0 ? (
                <div className="text-center p-6 bg-gray-800 rounded-lg border border-gray-700">
                    <p className="text-gray-400">No upcoming games scheduled for this period</p>
                </div>
            ) : (
                <div className="space-y-8">
                    {Object.entries(groupedGames).map(([date, dateGames]) => (
                        <div key={date} className="space-y-4">
                            <h3 className="text-lg font-semibold text-white border-b border-gray-700 pb-2">
                                {date}
                            </h3>

                            <div className="space-y-2">
                                {dateGames.map((game) => (
                                    <div
                                        key={game.id}
                                        className="border border-gray-700 rounded overflow-hidden"
                                    >
                                        <div className="p-4">
                                            <div className="flex justify-between items-center mb-3">
                                                <div className="flex items-center">
                                                    <span className="font-medium text-white">
                                                        {formatGameTime(game.date)}
                                                    </span>
                                                </div>
                                                <span className="text-sm bg-gray-700 text-gray-300 px-3 py-1 rounded">
                                                    Round {game.round || "?"}
                                                </span>
                                            </div>

                                            <div className="flex items-center justify-between my-3">
                                                {/* Home Team */}
                                                <div className="flex flex-col items-start w-5/12">
                                                    <span className={`text-lg font-bold ${
                                                        game.home_team?.club?.toLowerCase() === "mentone"
                                                            ? "text-blue-400"
                                                            : "text-white"
                                                    }`}>
                                                        {game.home_team?.name || "TBD"}
                                                    </span>
                                                    {game.home_team?.club?.toLowerCase() === "mentone" && (
                                                        <span className="text-xs text-gray-400">
                                                            {game.home_team.type || ""} {game.home_team.type && game.home_team.gender ? " - " : ""} {game.home_team.gender || ""}
                                                        </span>
                                                    )}
                                                </div>

                                                {/* VS */}
                                                <div className="flex items-center w-2/12 justify-center">
                                                    <span className="text-gray-400 text-sm font-medium">vs</span>
                                                </div>

                                                {/* Away Team */}
                                                <div className="flex flex-col items-end w-5/12">
                                                    <span className={`text-lg font-bold text-right ${
                                                        game.away_team?.club?.toLowerCase() === "mentone"
                                                            ? "text-blue-400"
                                                            : "text-white"
                                                    }`}>
                                                        {game.away_team?.name || "TBD"}
                                                    </span>
                                                    {game.away_team?.club?.toLowerCase() === "mentone" && (
                                                        <span className="text-xs text-gray-400 text-right">
                                                            {game.away_team.type || ""} {game.away_team.type && game.away_team.gender ? " - " : ""} {game.away_team.gender || ""}
                                                        </span>
                                                    )}
                                                </div>
                                            </div>

                                            <div className="mt-3 text-sm text-gray-400 flex items-center">
                                                <svg
                                                    xmlns="http://www.w3.org/2000/svg"
                                                    width="16"
                                                    height="16"
                                                    viewBox="0 0 24 24"
                                                    fill="none"
                                                    stroke="currentColor"
                                                    strokeWidth="2"
                                                    strokeLinecap="round"
                                                    strokeLinejoin="round"
                                                    className="mr-1"
                                                >
                                                    <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"></path>
                                                    <circle cx="12" cy="10" r="3"></circle>
                                                </svg>
                                                <span>{game.venue || "Venue TBD"}</span>
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