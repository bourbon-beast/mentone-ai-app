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
        if (team?.name && team.name.includes(" - ")) {
            const compName = team.name.split(" - ")[1];
            return compName.replace(/ - \d{4}$/, "");
        }

        const fixtureId = game.fixture_id;
        if (fixtureId && gradeData[fixtureId]) {
            const gradeName = gradeData[fixtureId].name;
            return gradeName.replace(/ - \d{4}$/, "");
        }

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
        return <div className="text-center p-4 text-mentone-offwhite">Loading upcoming games...</div>;
    }

    if (error) {
        return <div className="text-center p-4 text-red-400">Error: {error}</div>;
    }

    const groupedGames = groupGamesByDate();

    return (
        <div className="p-4 bg-mentone-navy rounded-lg">
            <div className="flex justify-between items-center mb-6">
                <h2 className="text-2xl font-bold text-mentone-gold">Upcoming Games</h2>

                <div className="flex space-x-1">
                    <button
                        onClick={() => setDateFilter("thisWeek")}
                        className={`px-3 py-1 text-sm rounded transition-colors ${
                            dateFilter === "thisWeek"
                                ? "bg-mentone-skyblue text-mentone-offwhite"
                                : "bg-mentone-navy text-mentone-offwhite hover:bg-mentone-skyblue hover:bg-opacity-70"
                        }`}
                        style={{backgroundColor: dateFilter === "thisWeek" ? "#4A90E2" : "#1B1F4A"}}
                    >
                        This Week
                    </button>
                    <button
                        onClick={() => setDateFilter("nextWeek")}
                        className={`px-3 py-1 text-sm rounded transition-colors ${
                            dateFilter === "nextWeek"
                                ? "bg-mentone-skyblue text-mentone-offwhite"
                                : "bg-mentone-navy text-mentone-offwhite hover:bg-mentone-skyblue hover:bg-opacity-70"
                        }`}
                        style={{backgroundColor: dateFilter === "nextWeek" ? "#4A90E2" : "#1B1F4A"}}
                    >
                        Next Week
                    </button>
                    <button
                        onClick={() => setDateFilter("twoWeeks")}
                        className={`px-3 py-1 text-sm rounded transition-colors ${
                            dateFilter === "twoWeeks"
                                ? "bg-mentone-skyblue text-mentone-offwhite"
                                : "bg-mentone-navy text-mentone-offwhite hover:bg-mentone-skyblue hover:bg-opacity-70"
                        }`}
                        style={{backgroundColor: dateFilter === "twoWeeks" ? "#4A90E2" : "#1B1F4A"}}
                    >
                        Two Weeks
                    </button>
                </div>
            </div>

            {games.length === 0 ? (
                <div className="text-center p-6 bg-mentone-charcoal bg-opacity-50 rounded-lg border border-mentone-skyblue"
                     style={{backgroundColor: "#4A4A4A", borderColor: "#4A90E2"}}>
                    <p className="text-mentone-offwhite" style={{color: "#F4F4F4"}}>No upcoming games scheduled for this period</p>
                </div>
            ) : (
                <div className="space-y-8">
                    {Object.entries(groupedGames).map(([date, dateGames]) => (
                        <div key={date} className="space-y-2">
                            <h3 className="text-lg font-semibold text-mentone-yellow border-b border-mentone-skyblue pb-2"
                                style={{color: "#F9E547", borderColor: "#4A90E2"}}>
                                {date}
                            </h3>

                            <div className="space-y-2">
                                {dateGames.map((game) => {
                                    const isMentoneHome = game.home_team?.club?.toLowerCase() === "mentone";
                                    const isMentoneAway = game.away_team?.club?.toLowerCase() === "mentone";
                                    const mentoneTeam = isMentoneHome ? game.home_team : game.away_team;
                                    const competitionName = mentoneTeam ? getCompetitionName(game, mentoneTeam) : "";

                                    return (
                                        <div
                                            key={game.id}
                                            className="border border-mentone-skyblue rounded-md overflow-hidden bg-mentone-charcoal bg-opacity-30 hover:bg-opacity-40 transition-colors"
                                            style={{borderColor: "#4A90E2", backgroundColor: "#4A4A4A"}}
                                        >
                                            <div className="p-4">
                                                {/* Competition name */}
                                                <div className="flex justify-center mb-3">
                                                    <span className="text-mentone-gold font-bold" style={{color: "#FFD700"}}>
                                                        {competitionName}
                                                    </span>
                                                </div>

                                                {/* Time and venue */}
                                                <div className="flex justify-between text-mentone-grey text-sm mb-3">
                                                    <div className="flex items-center gap-1">
                                                        🕒 <span>{formatGameTime(game.date)}</span>
                                                    </div>
                                                    <div className="flex items-center gap-1">
                                                        📍 <span>{game.venue || "Venue TBD"}</span>
                                                    </div>
                                                </div>

                                                {/* Teams */}
                                                <div className="flex items-center justify-between text-sm">
                                                    <div className="w-5/12 text-right pr-2">
                                                        <span
                                                            style={{
                                                                color: isMentoneHome ? "#4A90E2" : "#F4F4F4",
                                                                fontWeight: "bold"
                                                            }}
                                                        >
                                                            {isMentoneHome ? "Mentone" : game.home_team?.name || "TBD"}
                                                        </span>
                                                    </div>
                                                    <div className="w-2/12 text-center">
                                                        <span style={{color: "#C0C0C0"}} className="text-sm font-medium">vs</span>
                                                    </div>
                                                    <div className="w-5/12 text-left pl-2">
                                                        <span
                                                            style={{
                                                                color: isMentoneAway ? "#4A90E2" : "#F4F4F4",
                                                                fontWeight: "bold"
                                                            }}
                                                        >
                                                            {isMentoneAway ? "Mentone" : game.away_team?.name || "TBD"}
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