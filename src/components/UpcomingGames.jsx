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

    // Format date as "Saturday 26 Apr"
    const formatGameDate = (date) => {
        if (!date) return "TBD";
        const gameDate = date.toDate ? date.toDate() : new Date(date);
        return gameDate.toLocaleDateString('en-AU', {
            weekday: 'long',
            day: 'numeric',
            month: 'short'
        });
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
            const dateStr = formatGameDate(gameDate);

            if (!grouped[dateStr]) {
                grouped[dateStr] = [];
            }

            grouped[dateStr].push(game);
        });

        return grouped;
    };

    if (loading) {
        return (
            <div className="flex items-center justify-center h-64 bg-white rounded-xl shadow-sm">
                <div className="flex flex-col items-center">
                    <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-mentone-skyblue mb-2"></div>
                    <p className="text-mentone-navy font-medium">Loading upcoming games...</p>
                </div>
            </div>
        );
    }

    if (error) {
        return (
            <div className="bg-red-50 border border-red-200 rounded-xl p-5 text-red-600">
                <p className="font-medium mb-1">Error</p>
                <p className="text-sm">{error}</p>
            </div>
        );
    }

    const groupedGames = groupGamesByDate();

    return (
        <div className="bg-white rounded-xl shadow-sm overflow-hidden">
            {/* Header section */}
            <div className="bg-gradient-to-r from-mentone-navy to-mentone-navy/90 p-5 flex justify-between items-center">
                <h2 className="text-2xl font-bold text-mentone-gold tracking-tight">Upcoming Games</h2>

                <div className="bg-mentone-navy/50 backdrop-blur-sm rounded-lg p-1 flex">
                    {[
                        { value: "thisWeek", label: "This Week" },
                        { value: "nextWeek", label: "Next Week" },
                        { value: "twoWeeks", label: "Two Weeks" }
                    ].map((filter) => (
                        <button
                            key={filter.value}
                            onClick={() => setDateFilter(filter.value)}
                            className={`px-4 py-2 text-sm font-medium rounded-md transition-all ${
                                dateFilter === filter.value
                                    ? "bg-mentone-skyblue text-white shadow-sm"
                                    : "text-white/80 hover:bg-mentone-navy/70 hover:text-white"
                            }`}
                        >
                            {filter.label}
                        </button>
                    ))}
                </div>
            </div>

            {/* Game listings */}
            <div className="p-5">
                {games.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-16 bg-gray-50 rounded-lg border border-gray-100">
                        <svg xmlns="http://www.w3.org/2000/svg" className="h-12 w-12 text-gray-300 mb-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                        </svg>
                        <p className="text-gray-500 font-medium">No upcoming games scheduled for this period</p>
                        <p className="text-gray-400 text-sm mt-1">Try selecting a different time period</p>
                    </div>
                ) : (
                    <div className="space-y-8">
                        {Object.entries(groupedGames).map(([date, dateGames]) => (
                            <div key={date} className="relative">
                                <div className="sticky top-0 bg-white z-10 pt-1 pb-3">
                                    <h3 className="inline-block px-4 py-1.5 bg-mentone-gold/10 text-mentone-navy font-bold rounded-full text-sm">
                                        {date}
                                    </h3>
                                </div>

                                <div className="space-y-4">
                                    {dateGames.map((game) => {
                                        const isMentoneHome = game.home_team?.club?.toLowerCase() === "mentone";
                                        const isMentoneAway = game.away_team?.club?.toLowerCase() === "mentone";
                                        const mentoneTeam = isMentoneHome ? game.home_team : game.away_team;
                                        const competitionName = mentoneTeam ? getCompetitionName(game, mentoneTeam) : "";

                                        return (
                                            <div
                                                key={game.id}
                                                className="bg-white border border-gray-100 rounded-xl overflow-hidden shadow-sm hover:shadow-md transition-shadow duration-300 transform hover:translate-y-[-2px]"
                                            >
                                                {/* Competition badge */}
                                                <div className="bg-gray-50 px-4 py-2 border-b border-gray-100 flex justify-between items-center">
                                                    <div className="flex items-center">
                            <span className="font-semibold text-mentone-navy">
                              {competitionName}
                            </span>
                                                    </div>
                                                    <div className="flex items-center space-x-2">
                                                        {game.round && (
                                                            <span className="text-xs px-2 py-0.5 bg-mentone-gold/80 text-mentone-navy rounded-full font-medium">
                                Round {game.round}
                              </span>
                                                        )}
                                                        <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                                                            competitionName.includes("Premier")
                                                                ? "bg-mentone-navy text-white"
                                                                : competitionName.includes("Pennant") || competitionName.includes("Vic League")
                                                                    ? "bg-mentone-skyblue text-white"
                                                                    : competitionName.includes("Metro")
                                                                        ? "bg-mentone-green/70 text-white"
                                                                        : "bg-gray-200 text-gray-700"
                                                        }`}>
                              {competitionName.includes("Men") ? "Men" : competitionName.includes("Women") ? "Women" : "Mixed"}
                            </span>
                                                    </div>
                                                </div>

                                                <div className="p-4">
                                                    {/* Teams Section */}
                                                    <div className="flex items-center justify-between mb-5">
                                                        {/* Home Team */}
                                                        <div className="flex flex-col items-center w-5/12">
                                                            <div className={`w-12 h-12 flex items-center justify-center mb-2 ${
                                                                isMentoneHome
                                                                    ? "bg-mentone-navy text-white rounded-full"
                                                                    : "bg-gray-100 text-gray-600 rounded-full"
                                                            }`}>
                                <span className={isMentoneHome ? "text-white font-bold" : "text-gray-600 font-medium"}>
                                  {(game.home_team?.name || "TBD").substring(0, 1)}
                                </span>
                                                            </div>
                                                            <span className={`text-center font-medium ${isMentoneHome ? "text-mentone-skyblue" : "text-gray-700"}`}>
                                {isMentoneHome ? "Mentone" : game.home_team?.name || "TBD"}
                              </span>
                                                        </div>

                                                        {/* VS */}
                                                        <div className="flex flex-col items-center justify-center">
                                                            <span className="text-gray-400 text-sm font-medium">vs</span>
                                                        </div>

                                                        {/* Away Team */}
                                                        <div className="flex flex-col items-center w-5/12">
                                                            <div className={`w-12 h-12 flex items-center justify-center mb-2 ${
                                                                isMentoneAway
                                                                    ? "bg-mentone-navy text-white rounded-full"
                                                                    : "bg-gray-100 text-gray-600 rounded-full"
                                                            }`}>
                                <span className={isMentoneAway ? "text-white font-bold" : "text-gray-600 font-medium"}>
                                  {(game.away_team?.name || "TBD").substring(0, 1)}
                                </span>
                                                            </div>
                                                            <span className={`text-center font-medium ${isMentoneAway ? "text-mentone-skyblue" : "text-gray-700"}`}>
                                {isMentoneAway ? "Mentone" : game.away_team?.name || "TBD"}
                              </span>
                                                        </div>
                                                    </div>

                                                    {/* Game Info */}
                                                    <div className="flex justify-between items-center pt-3 border-t border-gray-100">
                                                        <div className="flex items-center text-gray-600">
                                                            <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                                                            </svg>
                                                            <span className="text-sm">{formatGameTime(game.date)}</span>
                                                        </div>

                                                        <div className="flex items-center text-gray-600">
                                                            <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
                                                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
                                                            </svg>
                                                            <span className="text-sm truncate max-w-[180px]">{game.venue || "Venue TBD"}</span>
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
        </div>
    );
};

export default UpcomingGames;