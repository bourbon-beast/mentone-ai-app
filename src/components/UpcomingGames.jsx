import { useState, useEffect, useRef } from "react";
import { collection, query, where, orderBy, limit, getDocs } from "firebase/firestore";
import { db } from "../firebase";
import { useFavorites } from "../context/FavoritesContext";
import FilterByFavorites from "./common/FilterByFavorites";
import FavoriteButton from "./common/FavoriteButton";


const UpcomingGames = () => {
    const [games, setGames] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [dateFilter, setDateFilter] = useState("thisWeek");
    const [gradeData, setGradeData] = useState({});
    const [textCopied, setTextCopied] = useState(false);
    const tableContainerRef = useRef(null);
    const { showOnlyFavorites, favoriteTeams } = useFavorites();

    // Team filtering state
    const [mentoneTeams, setMentoneTeams] = useState([]);
    const [selectedTeams, setSelectedTeams] = useState([]); // Stores { id, fixture_id, name }
    const [teamFilterOpen, setTeamFilterOpen] = useState(false);

    // Fetch mentone teams
    useEffect(() => {
        const fetchMentoneTeams = async () => {
            try {
                const teamsQuery = query(
                    collection(db, "teams"),
                    where("is_home_club", "==", true),
                    orderBy("type"),
                    orderBy("name"),
                    limit(100)
                );

                const teamsSnapshot = await getDocs(teamsQuery);

                if (teamsSnapshot.empty) {
                    console.warn("No Mentone teams found in database");
                    setMentoneTeams([]);
                } else {
                    const teamsData = teamsSnapshot.docs.map(doc => ({
                        id: doc.id,
                        ...doc.data()
                    }));

                    // Validation: Check if teams have fixture_id
                    const teamsWithoutFixtureId = teamsData.filter(t => !t.fixture_id);
                    if (teamsWithoutFixtureId.length > 0) {
                        console.warn(`Warning: ${teamsWithoutFixtureId.length} Mentone teams missing 'fixture_id'. Filtering might be incomplete.`, teamsWithoutFixtureId.map(t => t.name));
                    }

                    console.log(`Loaded ${teamsData.length} Mentone teams`);
                    setMentoneTeams(teamsData);
                }
            } catch (err) {
                console.error("Error fetching Mentone teams:", err);
            }
        };

        fetchMentoneTeams();
    }, []);

    // Fetch games and grade data
    useEffect(() => {
        const fetchData = async () => {
            try {
                setLoading(true);
                setError(null);

                // Fetch all grades
                const gradesRef = collection(db, "grades");
                const gradesSnapshot = await getDocs(gradesRef);

                const gradesMap = {};
                gradesSnapshot.forEach(doc => {
                    const data = doc.data();
                    gradesMap[doc.id] = data;
                });

                setGradeData(gradesMap);

                // Fetch games
                await fetchUpcomingGames(dateFilter);
            } catch (err) {
                console.error("Error fetching data:", err);
                setError(err.message);
            } finally {
                setLoading(false);
            }
        };

        fetchData();
    }, [dateFilter]);

    // Get current round date range (Friday to Wednesday)
    const getRoundDateRange = (weekOffset = 0) => {
        const now = new Date();
        const currentDay = now.getDay();
        const daysToLastFriday = currentDay >= 5 ? currentDay - 5 : currentDay + 2;
        const lastFriday = new Date(now);
        lastFriday.setDate(now.getDate() - daysToLastFriday + (weekOffset * 7));
        lastFriday.setHours(0, 0, 0, 0);

        const nextWednesday = new Date(lastFriday);
        nextWednesday.setDate(lastFriday.getDate() + 5);
        nextWednesday.setHours(23, 59, 59, 999);

        return { startDate: lastFriday, endDate: nextWednesday };
    };

    // Function to fetch games
    const fetchUpcomingGames = async (filter) => {
        try {
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

            console.log(`Fetching games from ${dateRange.startDate.toISOString()} to ${dateRange.endDate.toISOString()}`);

            const gamesQuery = query(
                collection(db, "games"),
                where("date", ">=", dateRange.startDate),
                where("date", "<=", dateRange.endDate),
                where("mentone_playing", "==", true),
                orderBy("date", "asc"),
                limit(100)
            );

            const querySnapshot = await getDocs(gamesQuery);
            const gamesData = querySnapshot.docs.map(doc => ({
                id: doc.id,
                ...doc.data()
            }));

            console.log(`Fetched ${gamesData.length} games where mentone_playing is true.`);

            const gamesWithoutFixtureId = gamesData.filter(g => !g.fixture_id);
            if (gamesWithoutFixtureId.length > 0) {
                console.warn(`Warning: ${gamesWithoutFixtureId.length} fetched games missing 'fixture_id'. Competition naming/filtering might be incomplete.`);
            }

            setGames(gamesData);
        } catch (err) {
            console.error("Error fetching upcoming games:", err);
            setError(err.message);
            setGames([]);
        }
    };

    // Apply team filters
    const filteredGames = selectedTeams.length > 0
        ? games.filter(game => {
            // Game must have a fixture_id to be filterable by team selection
            if (!game.fixture_id) return false;

            // Check if the game's fixture_id matches any selected team's fixture_id
            return selectedTeams.some(selectedTeam =>
                selectedTeam.fixture_id === game.fixture_id
            );
        })
        : showOnlyFavorites
            ? games.filter(game => {
                // If showing only favorites, check if game fixture_id is in any favorite team's fixture_id
                return favoriteTeams.some(favTeam => favTeam.fixture_id === game.fixture_id);
            })
            : games; // If no teams selected and not filtering by favorites, show all fetched games

    // Handler for toggling team selection
    const toggleTeamSelection = (team) => {
        if (!team.fixture_id) {
            console.warn(`Cannot select team "${team.name}" (ID: ${team.id}) as it lacks a fixture_id.`);
            return;
        }
        setSelectedTeams(prevSelected => {
            const isSelected = prevSelected.some(t => t.id === team.id);
            if (isSelected) {
                return prevSelected.filter(t => t.id !== team.id);
            } else {
                return [...prevSelected, {
                    id: team.id,
                    fixture_id: team.fixture_id,
                    name: team.name
                }];
            }
        });
    };

    // Handler for clearing all team selections
    const clearTeamSelections = () => {
        setSelectedTeams([]);
    };

    // Get human-readable date range for filter
    const getFilterDateRangeText = (filter) => {
        let dateRange;
        if (filter === "thisWeek") dateRange = getRoundDateRange(0);
        else if (filter === "nextWeek") dateRange = getRoundDateRange(1);
        else if (filter === "twoWeeks") {
            const currentRound = getRoundDateRange(0);
            const nextRound = getRoundDateRange(1);
            dateRange = { startDate: currentRound.startDate, endDate: nextRound.endDate };
        }

        const formatDate = (date) => date.toLocaleDateString('en-AU', { day: 'numeric', month: 'short' });
        return `${formatDate(dateRange.startDate)} - ${formatDate(dateRange.endDate)}`;
    };

    // Get competition name by fixture ID
    const getCompetitionName = (game) => {
        const fixtureId = game.fixture_id;
        if (fixtureId && gradeData[fixtureId]) {
            const gradeName = gradeData[fixtureId].name || `Grade ${fixtureId}`;
            return gradeName.replace(/ - \d{4}$/, "");
        }
        return `Unknown Competition`;
    };

    // Get opponent team
    const getOpponentTeam = (game) => {
        const isMentoneHome = game.home_team?.club?.toLowerCase().includes("mentone");
        return isMentoneHome ? game.away_team : game.home_team;
    };

    // Format date as "Saturday 26 Apr"
    const formatGameDate = (date) => {
        if (!date) return "TBD";
        const gameDate = date.toDate ? date.toDate() : new Date(date);
        return gameDate.toLocaleDateString('en-AU', {
            weekday: 'long',
            day: 'numeric',
            month: 'short',
            timeZone: 'UTC'
        });
    };

    // Format time only (HH:MM)
    const formatGameTime = (date) => {
        if (!date) return "TBD";
        const gameDate = date.toDate ? date.toDate() : new Date(date);
        return gameDate.toLocaleTimeString('en-AU', {
            hour: '2-digit',
            minute: '2-digit',
            hour12: false,
            timeZone: 'UTC'
        });
    };

    // Generate HTML table for games
    const generateHTMLTable = () => {
        if (filteredGames.length === 0) return "<p>No upcoming games found for the selected criteria.</p>";

        let html = `<div style="font-family: Arial, sans-serif; max-width: 100%;">
            <h2 style="text-align: center; color: #1B1F4A; margin-bottom: 20px;">MENTONE HOCKEY CLUB - UPCOMING GAMES (${getFilterDateRangeText(dateFilter)})</h2>
            <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px;">
                <tr style="background-color: #f2f2f2;">
                    <th style="padding: 8px; text-align: left; border-bottom: 1px solid #ddd;">Date</th>
                    <th style="padding: 8px; text-align: left; border-bottom: 1px solid #ddd;">Time</th>
                    <th style="padding: 8px; text-align: left; border-bottom: 1px solid #ddd;">Competition</th>
                    <th style="padding: 8px; text-align: left; border-bottom: 1px solid #ddd;">Playing</th>
                    <th style="padding: 8px; text-align: left; border-bottom: 1px solid #ddd;">Venue</th>
                </tr>`;

        filteredGames.forEach((game, index) => {
            const date = formatGameDate(game.date);
            const time = formatGameTime(game.date);
            const opponent = getOpponentTeam(game);
            const opponentName = opponent?.name?.replace(" Hockey Club", "") || "TBD";
            const competition = getCompetitionName(game);
            const venue = game.venue || "Venue TBD";

            const rowStyle = index % 2 === 0 ? "" : "background-color: #f9f9f9;";

            html += `
                <tr style="${rowStyle}">
                    <td style="padding: 8px; text-align: left; border-bottom: 1px solid #ddd;">${date}</td>
                    <td style="padding: 8px; text-align: left; border-bottom: 1px solid #ddd;">${time}</td>
                    <td style="padding: 8px; text-align: left; border-bottom: 1px solid #ddd;">${competition}</td>
                    <td style="padding: 8px; text-align: left; border-bottom: 1px solid #ddd;">${opponentName}</td>
                    <td style="padding: 8px; text-align: left; border-bottom: 1px solid #ddd;">${venue}</td>
                </tr>`;
        });

        html += `</table></div>`;
        return html;
    };

    // Copy HTML to clipboard
    const copyHTMLToClipboard = () => {
        const htmlContent = generateHTMLTable();
        const tempEl = document.createElement('div');
        tempEl.innerHTML = htmlContent;
        document.body.appendChild(tempEl);

        const range = document.createRange();
        range.selectNodeContents(tempEl);
        const selection = window.getSelection();
        selection.removeAllRanges();
        selection.addRange(range);

        try {
            document.execCommand('copy');
            setTextCopied(true);
            setTimeout(() => setTextCopied(false), 2000);
        } catch (err) {
            console.error("Failed to copy HTML table:", err);
        } finally {
            selection.removeAllRanges();
            document.body.removeChild(tempEl);
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
                <p className="font-medium mb-1">Error Loading Games</p>
                <p className="text-sm">{error}</p>
            </div>
        );
    }

    // Prepare data for rendering
    const teamsByType = mentoneTeams.reduce((acc, team) => {
        const type = team.type || "Other";
        if (!acc[type]) acc[type] = [];
        acc[type].push(team);
        return acc;
    }, {});

    // Render
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

            {/* Controls: Date range, Team filter */}
            <div className="bg-mentone-navy/5 px-5 py-2 border-b border-gray-100 flex justify-between items-center">
                <div className="flex items-center gap-3">
                    {/* Date Range Display */}
                    <p className="text-mentone-navy text-sm font-medium">
                        Showing games: {getFilterDateRangeText(dateFilter)}
                    </p>
                    {/* Add the FilterByFavorites button here */}
                    <FilterByFavorites buttonSize="sm" variant="outline" />

                    {/* Team filter dropdown */}
                    <div className="relative">
                        <button
                            onClick={() => setTeamFilterOpen(!teamFilterOpen)}
                            className={`flex items-center gap-2 text-sm px-3 py-1.5 rounded-lg border transition-colors ${
                                selectedTeams.length > 0
                                    ? "bg-mentone-skyblue text-white border-mentone-skyblue"
                                    : "bg-white text-mentone-navy border-gray-300 hover:border-mentone-skyblue"
                            }`}
                        >
                            <svg
                                xmlns="http://www.w3.org/2000/svg"
                                className="h-4 w-4"
                                fill="none"
                                viewBox="0 0 24 24"
                                stroke="currentColor"
                            >
                                <path
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                    strokeWidth={2}
                                    d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z"
                                />
                            </svg>
                            {selectedTeams.length === 0 ? (
                                <span>Filter Teams</span>
                            ) : (
                                <span>
                                    {selectedTeams.length} team{selectedTeams.length !== 1 ? 's' : ''} selected
                                </span>
                            )}
                            <svg
                                xmlns="http://www.w3.org/2000/svg"
                                className={`h-4 w-4 transition-transform ${teamFilterOpen ? 'rotate-180' : ''}`}
                                fill="none"
                                viewBox="0 0 24 24"
                                stroke="currentColor"
                            >
                                <path
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                    strokeWidth={2}
                                    d="M19 9l-7 7-7-7"
                                />
                            </svg>
                        </button>

                        {teamFilterOpen && (
                            <div className="absolute z-20 top-full left-0 mt-1 bg-white border border-gray-200 rounded-lg shadow-lg w-72 max-h-96 overflow-y-auto">
                                <div className="sticky top-0 bg-white px-4 py-2 border-b border-gray-100 flex justify-between items-center">
                                    <h3 className="text-sm font-semibold text-mentone-navy">Filter by team</h3>
                                    <button
                                        onClick={clearTeamSelections}
                                        className="text-xs text-mentone-skyblue hover:text-mentone-navy"
                                    >
                                        Clear all
                                    </button>
                                </div>
                                <div className="p-2">
                                    {mentoneTeams.length === 0 ? (
                                        <div className="py-3 px-2 text-sm text-gray-500 text-center">
                                            Loading teams...
                                        </div>
                                    ) : (
                                        Object.entries(teamsByType).map(([type, typeTeams]) => (
                                            <div key={type} className="mb-3">
                                                <h4 className="text-xs font-bold px-2 py-1 bg-gray-100 rounded-md text-mentone-navy mb-1">
                                                    {type}
                                                </h4>
                                                <div className="space-y-1">
                                                    {typeTeams.map(team => {
                                                        const compName = team.name.includes(" - ") ? team.name.split(" - ")[1] : team.name;
                                                        const isSelected = selectedTeams.some(t => t.id === team.id);
                                                        const isDisabled = !team.fixture_id;
                                                        return (
                                                            <div
                                                                key={team.id}
                                                                className={`flex items-center pl-2 ${isDisabled ? 'opacity-50 cursor-not-allowed' : ''}`}
                                                            >
                                                                <input
                                                                    type="checkbox"
                                                                    id={`team-${team.id}`}
                                                                    checked={isSelected}
                                                                    onChange={() => toggleTeamSelection(team)}
                                                                    disabled={isDisabled}
                                                                    className="h-4 w-4 text-mentone-skyblue rounded border-gray-300 focus:ring-mentone-skyblue disabled:text-gray-400"
                                                                />
                                                                <label
                                                                    htmlFor={`team-${team.id}`}
                                                                    title={isDisabled ? `Cannot filter by this team (missing fixture_id)` : compName}
                                                                    className={`ml-2 text-sm text-gray-700 ${isDisabled ? 'cursor-not-allowed' : 'cursor-pointer'}`}
                                                                >
                                                                    {compName}
                                                                </label>
                                                            </div>
                                                        );
                                                    })}
                                                </div>
                                            </div>
                                        ))
                                    )}
                                </div>
                            </div>
                        )}
                    </div>
                </div>
            </div>

            {/* Show active filters if teams are selected */}
            {selectedTeams.length > 0 && (
                <div className="bg-mentone-skyblue/5 px-5 py-2 border-b border-mentone-skyblue/10">
                    <div className="flex flex-wrap items-center gap-2">
                        <span className="text-xs font-medium text-mentone-navy">Active filters:</span>
                        {selectedTeams.map(team => {
                            const compName = team.name.includes(" - ") ? team.name.split(" - ")[1] : team.name;
                            return (
                                <div
                                    key={team.id}
                                    className="bg-mentone-skyblue/10 text-mentone-skyblue text-xs px-2 py-1 rounded-full flex items-center"
                                >
                                    <span className="mr-1">{compName}</span>
                                    <button
                                        onClick={() => toggleTeamSelection(team)}
                                        className="hover:text-mentone-navy"
                                        title={`Remove ${compName} filter`}
                                    >
                                        <svg
                                            xmlns="http://www.w3.org/2000/svg"
                                            className="h-3 w-3"
                                            viewBox="0 0 20 20"
                                            fill="currentColor"
                                        >
                                            <path
                                                fillRule="evenodd"
                                                d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
                                                clipRule="evenodd"
                                            />
                                        </svg>
                                    </button>
                                </div>
                            );
                        })}
                        <button
                            onClick={clearTeamSelections}
                            className="text-xs text-mentone-skyblue hover:text-mentone-navy ml-1"
                        >
                            Clear all
                        </button>
                    </div>
                </div>
            )}

            {/* Game listings - Single Table View */}
            <div className="p-3">
                {filteredGames.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-8 bg-gray-50 rounded border border-gray-100">
                        <svg
                            xmlns="http://www.w3.org/2000/svg"
                            className="h-10 w-10 text-gray-300 mb-2"
                            fill="none"
                            viewBox="0 0 24 24"
                            stroke="currentColor"
                        >
                            <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                strokeWidth={1.5}
                                d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"
                            />
                        </svg>
                        <p className="text-gray-500 text-sm">No upcoming games</p>
                        <p className="text-gray-400 text-xs mt-1">
                            {selectedTeams.length > 0 ? "Adjust teams or date range" : "Adjust time period"}
                        </p>
                    </div>
                ) : (
                    <div>
                        {/* Copy button */}
                        <div className="flex justify-end mb-2">
                            <button
                                onClick={copyHTMLToClipboard}
                                className={`px-3 py-1 rounded text-white text-xs flex items-center ${
                                    textCopied ? 'bg-green-600' : 'bg-mentone-skyblue hover:bg-mentone-skyblue/90'
                                } transition-colors`}
                            >
                                {textCopied ? (
                                    <>✓ Copied!</>
                                ) : (
                                    <>⧉ Copy HTML</>
                                )}
                            </button>
                        </div>

                        {/* Single Table Display */}
                        <div ref={tableContainerRef} className="overflow-auto bg-white rounded border border-gray-200">
                            <table className="min-w-full divide-y divide-gray-200 text-xs">
                                <thead className="bg-gray-50">
                                <tr>
                                    <th className="px-2 py-1 text-left font-medium text-gray-500 uppercase">Date</th>
                                    <th className="px-2 py-1 text-left font-medium text-gray-500 uppercase">Time</th>
                                    <th className="px-2 py-1 text-left font-medium text-gray-500 uppercase">Competition</th>
                                    <th className="px-2 py-1 text-left font-medium text-gray-500 uppercase">Opponent</th>
                                    <th className="px-2 py-1 text-left font-medium text-gray-500 uppercase">Venue</th>
                                </tr>
                                </thead>
                                <tbody className="divide-y divide-gray-100">
                                {filteredGames.map((game, index) => {
                                    const opponentTeam = getOpponentTeam(game);
                                    const opponentName =
                                        opponentTeam?.name?.replace(" Hockey Club", "") ||
                                        opponentTeam?.club?.replace(" Hockey Club", "") ||
                                        "TBD";
                                    const competitionName = getCompetitionName(game);

                                    return (
                                        <tr key={game.id} className={index % 2 === 0 ? 'bg-white' : 'bg-gray-50'}>
                                            <td className="px-2 py-1 text-left text-gray-600 whitespace-nowrap">
                                                {formatGameDate(game.date)}
                                            </td>
                                            <td className="px-2 py-1 text-left text-gray-600 whitespace-nowrap">
                                                {formatGameTime(game.date)}
                                            </td>
                                            <td className="px-2 py-1 text-left text-gray-800 whitespace-nowrap">
                                                {competitionName}
                                            </td>
                                            <td className="px-2 py-1 text-left text-gray-800 whitespace-nowrap">
                                                {opponentName}
                                            </td>
                                            <td className="px-2 py-1 text-left text-gray-600 whitespace-nowrap">
                                                {(game.venue || "Venue TBD").trim()}
                                            </td>
                                        </tr>
                                    );
                                })}
                                </tbody>
                            </table>
                        </div>
                    </div>
                )}
            </div>

            {/* Optional Debug info */}
            {process.env.NODE_ENV === 'development' && (
                <div className="mt-4 p-2 border-t text-xs text-gray-500">
                    <p>Debug: {games.length} Mentone games fetched. {filteredGames.length} games shown after team filter. {selectedTeams.length} teams selected.</p>
                </div>
            )}
        </div>
    );
};

export default UpcomingGames;