import { useState, useEffect, useRef } from "react";
import { collection, query, where, orderBy, limit, getDocs } from "firebase/firestore";
import { db } from "../firebase";

const UpcomingGames = () => {
    const [games, setGames] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [dateFilter, setDateFilter] = useState("thisWeek");
    const [gradeData, setGradeData] = useState({});
    const [viewMode, setViewMode] = useState("cards"); // "cards" or "table"
    const [textCopied, setTextCopied] = useState(false);
    const tableContainerRef = useRef(null);

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

    // Get current round date range (Friday to Wednesday)
    const getRoundDateRange = (weekOffset = 0) => {
        const now = new Date();
        const currentDay = now.getDay(); // 0 = Sunday, 1 = Monday, ..., 5 = Friday, 6 = Saturday

        // Determine the most recent Friday
        const daysToLastFriday = currentDay >= 5 ? currentDay - 5 : currentDay + 2;
        const lastFriday = new Date(now);
        lastFriday.setDate(now.getDate() - daysToLastFriday + (weekOffset * 7));
        lastFriday.setHours(0, 0, 0, 0);

        // Set the end date to the upcoming Wednesday
        const nextWednesday = new Date(lastFriday);
        nextWednesday.setDate(lastFriday.getDate() + 5); // 5 days after Friday is Wednesday
        nextWednesday.setHours(23, 59, 59, 999);

        return { startDate: lastFriday, endDate: nextWednesday };
    };

    // Separate function to fetch games
    const fetchUpcomingGames = async (filter) => {
        try {
            let dateRange;

            // Calculate date range based on filter
            if (filter === "thisWeek") {
                dateRange = getRoundDateRange(0); // Current round
            } else if (filter === "nextWeek") {
                dateRange = getRoundDateRange(1); // Next round
            } else if (filter === "twoWeeks") {
                // For "Two Weeks", we'll show from current round start to next round end
                const currentRound = getRoundDateRange(0);
                const nextRound = getRoundDateRange(1);

                dateRange = {
                    startDate: currentRound.startDate,
                    endDate: nextRound.endDate
                };
            }

            const gamesQuery = query(
                collection(db, "games"),
                where("date", ">=", dateRange.startDate),
                where("date", "<=", dateRange.endDate),
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

    // Get human-readable date range for filter
    const getFilterDateRangeText = (filter) => {
        let dateRange;

        if (filter === "thisWeek") {
            dateRange = getRoundDateRange(0);
        } else if (filter === "nextWeek") {
            dateRange = getRoundDateRange(1);
        } else if (filter === "twoWeeks") {
            const currentRound = getRoundDateRange(0);
            const nextRound = getRoundDateRange(1);

            dateRange = {
                startDate: currentRound.startDate,
                endDate: nextRound.endDate
            };
        }

        const formatDate = (date) => {
            return date.toLocaleDateString('en-AU', {
                day: 'numeric',
                month: 'short'
            });
        };

        return `${formatDate(dateRange.startDate)} - ${formatDate(dateRange.endDate)}`;
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
    // Updated formatGameDate function
    const formatGameDate = (date) => {
        if (!date) return "TBD";

        const gameDate = date.toDate ? date.toDate() : new Date(date);

        return gameDate.toLocaleDateString('en-AU', {
            weekday: 'long',
            day: 'numeric',
            month: 'short',
            timeZone: 'UTC' // Explicitly use UTC to avoid local conversion
        });
    };

    // Format time only (HH:MM)
    const formatGameTime = (date) => {
        if (!date) return "TBD";

        // Use date directly without timezone adjustment
        const gameDate = date.toDate ? date.toDate() : new Date(date);

        return gameDate.toLocaleTimeString('en-AU', {
            hour: '2-digit',
            minute: '2-digit',
            hour12: false,
            timeZone: 'UTC' // Explicitly use UTC to avoid local conversion
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

    // Generate HTML table for games
    const generateHTMLTable = () => {
        if (games.length === 0) return "<p>No upcoming games scheduled for this period.</p>";

        const grouped = groupGamesByDate();
        let html = `<div style="font-family: Arial, sans-serif; max-width: 100%;">
            <h2 style="text-align: center; color: #1B1F4A; margin-bottom: 20px;">MENTONE HOCKEY CLUB - UPCOMING GAMES (${getFilterDateRangeText(dateFilter)})</h2>`;

        Object.entries(grouped).forEach(([date, dateGames]) => {
            html += `<h3 style="text-align: center; color: #1B1F4A; margin-top: 30px; margin-bottom: 10px; border-bottom: 1px solid #ddd; padding-bottom: 5px;">${date}</h3>`;

            // Start table
            html += `
            <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px;">
                <tr style="background-color: #f2f2f2;">
                    <th style="padding: 8px; text-align: left; border-bottom: 1px solid #ddd;">Time</th>
                    <th style="padding: 8px; text-align: left; border-bottom: 1px solid #ddd;">Competition</th>
                    <th style="padding: 8px; text-align: left; border-bottom: 1px solid #ddd;">Home Team</th>
                    <th style="padding: 8px; text-align: left; border-bottom: 1px solid #ddd;">Away Team</th>
                    <th style="padding: 8px; text-align: left; border-bottom: 1px solid #ddd;">Venue</th>
                </tr>`;

            dateGames.forEach((game, index) => {
                const time = formatGameTime(game.date);
                const isMentoneHome = game.home_team?.club?.toLowerCase() === "mentone";
                const isMentoneAway = game.away_team?.club?.toLowerCase() === "mentone";
                const mentoneTeam = isMentoneHome ? game.home_team : game.away_team;
                const competition = mentoneTeam ? getCompetitionName(game, mentoneTeam) : "";

                const homeTeam = isMentoneHome ? "Mentone" : game.home_team?.name || "TBD";
                const awayTeam = isMentoneAway ? "Mentone" : game.away_team?.name || "TBD";
                const venue = game.venue || "Venue TBD";

                // Alternate row colors for better readability
                const rowStyle = index % 2 === 0 ? "" : "background-color: #f9f9f9;";

                // Highlight Mentone in team columns
                const homeStyle = isMentoneHome ? "color: #4A90E2; font-weight: bold;" : "";
                const awayStyle = isMentoneAway ? "color: #4A90E2; font-weight: bold;" : "";

                html += `
                <tr style="${rowStyle}">
                    <td style="padding: 8px; text-align: left; border-bottom: 1px solid #ddd;">${time}</td>
                    <td style="padding: 8px; text-align: left; border-bottom: 1px solid #ddd;">${competition}</td>
                    <td style="padding: 8px; text-align: left; border-bottom: 1px solid #ddd; ${homeStyle}">${homeTeam}</td>
                    <td style="padding: 8px; text-align: left; border-bottom: 1px solid #ddd; ${awayStyle}">${awayTeam}</td>
                    <td style="padding: 8px; text-align: left; border-bottom: 1px solid #ddd;">${venue}</td>
                </tr>`;
            });

            // End table
            html += '</table>';
        });

        html += '</div>';
        return html;
    };

    // Copy HTML to clipboard
    const copyHTMLToClipboard = () => {
        if (tableContainerRef.current) {
            // Get the HTML content
            const htmlContent = generateHTMLTable();

            // Create a temporary element to copy from
            const tempEl = document.createElement('div');
            tempEl.innerHTML = htmlContent;
            document.body.appendChild(tempEl);

            // Select the content
            const range = document.createRange();
            range.selectNodeContents(tempEl);
            const selection = window.getSelection();
            selection.removeAllRanges();
            selection.addRange(range);

            // Copy to clipboard
            document.execCommand('copy');

            // Clean up
            selection.removeAllRanges();
            document.body.removeChild(tempEl);

            // Visual feedback
            setTextCopied(true);
            setTimeout(() => setTextCopied(false), 2000); // Reset after 2 seconds
        }
    };

    // Render loading state
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

    // Render error state
    if (error) {
        return (
            <div className="bg-red-50 border border-red-200 rounded-xl p-5 text-red-600">
                <p className="font-medium mb-1">Error</p>
                <p className="text-sm">{error}</p>
            </div>
        );
    }

    const groupedGames = groupGamesByDate();
    const htmlTable = generateHTMLTable();

    return (
        <div className="bg-white rounded-xl shadow-sm overflow-hidden">
            {/* Header section */}
            <div className="bg-gradient-to-r from-mentone-navy to-mentone-navy/90 p-5 flex justify-between items-center">
                <h2 className="text-2xl font-bold text-mentone-gold tracking-tight">Upcoming Games</h2>

                <div className="bg-mentone-navy/50 backdrop-blur-sm rounded-lg p-1 flex">
                    {[
                        { value: "thisWeek", label: "This Round" },
                        { value: "nextWeek", label: "Next Round" },
                        { value: "twoWeeks", label: "Two Rounds" }
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

            {/* Date range indicator and view switcher */}
            <div className="bg-mentone-navy/5 px-5 py-2 border-b border-gray-100 flex justify-between items-center">
                <p className="text-mentone-navy text-sm font-medium">
                    Showing games: {getFilterDateRangeText(dateFilter)}
                </p>

                {/* View mode toggle */}
                <div className="flex items-center bg-white border border-gray-200 rounded-lg overflow-hidden">
                    <button
                        onClick={() => setViewMode("cards")}
                        className={`px-3 py-1.5 text-sm font-medium flex items-center ${
                            viewMode === "cards"
                                ? "bg-mentone-skyblue text-white"
                                : "text-gray-700 hover:bg-gray-100"
                        }`}
                    >
                        <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
                        </svg>
                        Cards
                    </button>
                    <button
                        onClick={() => setViewMode("table")}
                        className={`px-3 py-1.5 text-sm font-medium flex items-center ${
                            viewMode === "table"
                                ? "bg-mentone-skyblue text-white"
                                : "text-gray-700 hover:bg-gray-100"
                        }`}
                    >
                        <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 10h18M3 14h18m-9-4v8m-7 0h14a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
                        </svg>
                        Table
                    </button>
                </div>
            </div>

            {/* Game listings - Card View */}
            {viewMode === "cards" && (
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
                                                        </div>
                                                    </div>

                                                    <div className="p-4">
                                                        {/* Teams Section */}
                                                        <div className="flex items-center justify-between mb-5">
                                                            {/* Home Team */}
                                                            <div className="flex flex-col items-center w-5/12">
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
            )}

            {/* Game listings - Table View */}
            {viewMode === "table" && (
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
                        <div>
                            {/* Copy button at the top of the table view */}
                            <div className="flex justify-end mb-4">
                                <button
                                    onClick={copyHTMLToClipboard}
                                    className={`px-4 py-2 rounded-lg text-white text-sm flex items-center ${textCopied ? 'bg-green-600' : 'bg-mentone-skyblue hover:bg-mentone-skyblue/90'} transition-colors`}
                                >
                                    {textCopied ? (
                                        <>
                                            <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                                            </svg>
                                            Copied to Clipboard!
                                        </>
                                    ) : (
                                        <>
                                            <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3" />
                                            </svg>
                                            Copy HTML for Email
                                        </>
                                    )}
                                </button>
                            </div>

                            {/* Table Display */}
                            <div
                                ref={tableContainerRef}
                                className="overflow-auto bg-white rounded-lg"
                            >
                                {Object.entries(groupedGames).map(([date, dateGames]) => (
                                    <div key={date} className="mb-8">
                                        <h3 className="text-lg font-bold text-mentone-navy mb-3 pb-2 border-b border-gray-200">
                                            {date}
                                        </h3>

                                        <div className="overflow-x-auto">
                                            <table className="min-w-full divide-y divide-gray-200">
                                                <thead className="bg-gray-50">
                                                <tr>
                                                    <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                                        Time
                                                    </th>
                                                    <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                                        Competition
                                                    </th>
                                                    <th scope="col" className="px-6 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">
                                                        Playing
                                                    </th>
                                                    <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                                        Venue
                                                    </th>
                                                </tr>
                                                </thead>

                                                <tbody className="bg-white divide-y divide-gray-200">
                                                {dateGames.map((game, index) => {
                                                    const isMentoneHome = game.home_team?.club?.toLowerCase() === "mentone";
                                                    const opponentTeam = isMentoneHome ? game.away_team : game.home_team;
                                                    const isMentoneOpponent = opponentTeam?.club?.toLowerCase() === "mentone"; // edge case safety

                                                    return (
                                                        <tr key={game.id} className={index % 2 === 0 ? 'bg-white' : 'bg-gray-50'}>
                                                            <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                                                                {formatGameTime(game.date)}
                                                            </td>
                                                            <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 text-left">
                                                                {getCompetitionName(game, isMentoneHome ? game.home_team : game.away_team)}
                                                            </td>
                                                            <td className="px-6 py-4 whitespace-nowrap text-sm text-center font-medium text-gray-900">
                                                                {isMentoneOpponent ? "TBD" : opponentTeam?.name || "TBD"}
                                                            </td>
                                                            <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                                                                {(game.venue || "Venue TBD").trim()}
                                                            </td>
                                                        </tr>
                                                    );
                                                })}
                                                </tbody>

                                            </table>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
};

export default UpcomingGames;