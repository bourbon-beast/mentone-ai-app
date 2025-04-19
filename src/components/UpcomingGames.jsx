import { useState, useEffect } from "react";
import { collection, query, where, orderBy, limit, getDocs } from "firebase/firestore";
import { db } from "../firebase";

const UpcomingGames = () => {
    const [games, setGames] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [dateFilter, setDateFilter] = useState("thisWeek");
    const [gradeData, setGradeData] = useState({});

    // Fetch games and grade data
    useEffect(() => {
        const fetchData = async () => {
            try {
                setLoading(true);

                // 1. Fetch all grades first to have names ready
                const gradesRef = collection(db, "grades");
                const gradesSnapshot = await getDocs(gradesRef);

                const gradesMap = {};
                gradesSnapshot.forEach(doc => {
                    const data = doc.data();
                    gradesMap[doc.id] = data;
                });

                setGradeData(gradesMap);

                // 2. Now fetch games with date filter
                await fetchUpcomingGames(dateFilter);

                setLoading(false);
            } catch (err) {
                console.error("Error fetching data:", err);
                setError(err.message);
                setLoading(false);
            }
        };

        fetchData();
    }, [dateFilter]);

    // Separate function to fetch games
    const fetchUpcomingGames = async (filter) => {
        try {
            // Get current date at midnight
            const now = new Date();
            now.setHours(0, 0, 0, 0);

            // Calculate end date based on filter
            const endDate = new Date(now);
            if (filter === "thisWeek") {
                endDate.setDate(now.getDate() + 7);
            } else if (filter === "nextWeek") {
                now.setDate(now.getDate() + 7);
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
        } catch (err) {
            console.error("Error fetching upcoming games:", err);
            setError(err.message);
        }
    };

    // Get competition name by fixture ID
    const getCompetitionName = (game, team) => {
        // First try to extract from team name - format: "Mentone - Competition Name"
        if (team?.name && team.name.includes(" - ")) {
            return team.name.split(" - ")[1];
        }

        // If that fails, try to get grade name from our grade data lookup
        const fixtureId = game.fixture_id;
        if (fixtureId && gradeData[fixtureId]) {
            return gradeData[fixtureId].name;
        }

        // Last resort, just show the fixture ID
        return `Grade ${fixtureId}`;
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
                        <div key={date} className="space-y-2">
                            <h3 className="text-lg font-semibold text-white border-b border-gray-700 pb-2">
                                {date}
                            </h3>

                            <div className="space-y-2">
                                {dateGames.map((game) => {
                                    // Determine which team is Mentone
                                    const isMentoneHome = game.home_team?.club?.toLowerCase() === "mentone";
                                    const isMentoneAway = game.away_team?.club?.toLowerCase() === "mentone";

                                    // Get the competition name from the Mentone team
                                    const mentoneTeam = isMentoneHome ? game.home_team : game.away_team;
                                    const competitionName = mentoneTeam ? getCompetitionName(game, mentoneTeam) : "";

                                    return (
                                        <div
                                            key={game.id}
                                            className="border border-gray-700 rounded overflow-hidden"
                                        >
                                            <div className="p-4">
                                                {/* 1. Competition name at the top */}
                                                <div className="flex justify-between items-center mb-3">
                                                    <span className="text-yellow-300 font-bold">
                                                        {competitionName}
                                                    </span>
                                                    <span className="text-sm bg-gray-700 text-gray-300 px-2 py-1 rounded">
                                                        Round {game.round || "?"}
                                                    </span>
                                                </div>

                                                {/* 2. Time and venue on second line */}
                                                <div className="flex items-center text-gray-400 text-sm mb-3">
                                                    <div className="flex items-center mr-4">
                                                        <svg
                                                            xmlns="http://www.w3.org/2000/svg"
                                                            width="14"
                                                            height="14"
                                                            viewBox="0 0 24 24"
                                                            fill="none"
                                                            stroke="currentColor"
                                                            strokeWidth="2"
                                                            strokeLinecap="round"
                                                            strokeLinejoin="round"
                                                            className="mr-1"
                                                        >
                                                            <circle cx="12" cy="12" r="10"></circle>
                                                            <polyline points="12 6 12 12 16 14"></polyline>
                                                        </svg>
                                                        <span>{formatGameTime(game.date)}</span>
                                                    </div>

                                                    <div className="flex items-center">
                                                        <svg
                                                            xmlns="http://www.w3.org/2000/svg"
                                                            width="14"
                                                            height="14"
                                                            viewBox="0 0 24 24"
                                                            fill="none"
                                                            stroke="currentColor"
                                                            strokeWidth="2"
                                                            strokeLinecap="round"
                                                            strokeLinejoin="round"
                                                            className="mr-1"
                                                        >
                                                            <circle cx="12" cy="10" r="3"></circle>
                                                            <path d="M12 21.7C17.3 17 20 13 20 10a8 8 0 1 0-16 0c0 3 2.7 6.9 8 11.7z"></path>
                                                        </svg>
                                                        <span>{game.venue || "Venue TBD"}</span>
                                                    </div>
                                                </div>

                                                {/* 3. Home and away team on third line */}
                                                <div className="flex items-center justify-between">
                                                    {/* Home Team */}
                                                    <div className="flex flex-col items-start w-5/12">
                                                        <span className={`font-bold ${
                                                            isMentoneHome
                                                                ? "text-blue-400"
                                                                : "text-white"
                                                        }`}>
                                                            {isMentoneHome
                                                                ? "Mentone"
                                                                : game.home_team?.name || "TBD"}
                                                        </span>
                                                    </div>

                                                    {/* VS */}
                                                    <div className="flex items-center w-2/12 justify-center">
                                                        <span className="text-gray-400 text-sm font-medium">vs</span>
                                                    </div>

                                                    {/* Away Team */}
                                                    <div className="flex flex-col items-end w-5/12">
                                                        <span className={`font-bold text-right ${
                                                            isMentoneAway
                                                                ? "text-blue-400"
                                                                : "text-white"
                                                        }`}>
                                                            {isMentoneAway
                                                                ? "Mentone"
                                                                : game.away_team?.name || "TBD"}
                                                        </span>
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
};

export default UpcomingGames;