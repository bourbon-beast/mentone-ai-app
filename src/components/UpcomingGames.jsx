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
                        ...doc.data() // Assuming team data includes 'fixture_id'
                    }));

                    // Validation: Check if teams have fixture_id
                    const teamsWithoutFixtureId = teamsData.filter(t => !t.fixture_id);
                    if (teamsWithoutFixtureId.length > 0) {
                        console.warn(`Warning: ${teamsWithoutFixtureId.length} Mentone teams missing 'fixture_id'. Filtering might be incomplete.`, teamsWithoutFixtureId.map(t=>t.name));
                    }

                    console.log(`Loaded ${teamsData.length} Mentone teams`);
                    setMentoneTeams(teamsData);
                }

            } catch (err) {
                console.error("Error fetching Mentone teams:", err);
                // Optionally set an error state specific to teams
            }
        };

        fetchMentoneTeams();
    }, []);

    // Fetch games and grade data
    useEffect(() => {
        const fetchData = async () => {
            try {
                setLoading(true);
                setError(null); // Clear previous errors

                // 1. Fetch all grades first to have names ready
                const gradesRef = collection(db, "grades");
                const gradesSnapshot = await getDocs(gradesRef);

                const gradesMap = {};
                gradesSnapshot.forEach(doc => {
                    const data = doc.data();
                    gradesMap[doc.id] = data; // Use doc.id (which should be fixture_id) as key
                });

                setGradeData(gradesMap);

                // 2. Now fetch games (filtered by mentone_playing in the query)
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
        const currentDay = now.getDay(); // 0 = Sunday, ..., 5 = Friday, 6 = Saturday
        const daysToLastFriday = currentDay >= 5 ? currentDay - 5 : currentDay + 2;
        const lastFriday = new Date(now);
        lastFriday.setDate(now.getDate() - daysToLastFriday + (weekOffset * 7));
        lastFriday.setHours(0, 0, 0, 0);

        const nextWednesday = new Date(lastFriday);
        nextWednesday.setDate(lastFriday.getDate() + 5);
        nextWednesday.setHours(23, 59, 59, 999);

        return { startDate: lastFriday, endDate: nextWednesday };
    };

    // --- UPDATED: Function to fetch games ---
    const fetchUpcomingGames = async (filter) => {
        try {
            let dateRange;

            // Calculate date range based on filter
            if (filter === "thisWeek") {
                dateRange = getRoundDateRange(0); // Current round
            } else if (filter === "nextWeek") {
                dateRange = getRoundDateRange(1); // Next round
            } else if (filter === "twoWeeks") {
                // Show from current round start to next round end
                const currentRound = getRoundDateRange(0);
                const nextRound = getRoundDateRange(1);
                dateRange = {
                    startDate: currentRound.startDate,
                    endDate: nextRound.endDate
                };
            }

            console.log(`Fetching games from ${dateRange.startDate.toISOString()} to ${dateRange.endDate.toISOString()}`);

            // --- UPDATED: Firestore Query for Games ---
            // NOTE: This now relies on the 'mentone_playing' boolean field existing
            const gamesQuery = query(
                collection(db, "games"),
                where("date", ">=", dateRange.startDate),
                where("date", "<=", dateRange.endDate),
                where("mentone_playing", "==", true), // <-- USE THE NEW FIELD HERE
                orderBy("date", "asc"),
                limit(100) // Keep limit reasonable
            );

            const querySnapshot = await getDocs(gamesQuery);
            const gamesData = querySnapshot.docs.map(doc => ({
                id: doc.id,
                ...doc.data()
            }));

            console.log(`Fetched ${gamesData.length} games where mentone_playing is true.`);

            // Validation: Check if games have fixture_id (optional but good practice)
            const gamesWithoutFixtureId = gamesData.filter(g => !g.fixture_id);
            if (gamesWithoutFixtureId.length > 0) {
                console.warn(`Warning: ${gamesWithoutFixtureId.length} fetched games missing 'fixture_id'. Competition naming/filtering might be incomplete.`);
            }

            setGames(gamesData); // Set state directly with Firestore results

        } catch (err) {
            console.error("Error fetching upcoming games:", err);
            setError(err.message); // Set error state
            setGames([]); // Clear games on error
        }
    };

    // Apply team filters (using fixture_id)
    // This filters the already-fetched Mentone games based on user's team selection
    const filteredGames = selectedTeams.length > 0
        ? games.filter(game => {
            // Game must have a fixture_id to be filterable by team selection
            if (!game.fixture_id) return false;

            // Check if the game's fixture_id matches any selected team's fixture_id
            return selectedTeams.some(selectedTeam =>
                selectedTeam.fixture_id === game.fixture_id
            );
        })
        : games; // If no teams selected, show all fetched (Mentone) games

    // Handler for toggling team selection (Stores fixture_id)
    const toggleTeamSelection = (team) => {
        // Ensure the team object has fixture_id before adding
        if (!team.fixture_id) {
            console.warn(`Cannot select team "${team.name}" (ID: ${team.id}) as it lacks a fixture_id.`);
            return; // Prevent adding team without fixture_id
        }
        setSelectedTeams(prevSelected => {
            const isSelected = prevSelected.some(t => t.id === team.id);
            if (isSelected) {
                // Remove team
                return prevSelected.filter(t => t.id !== team.id);
            } else {
                // Add team with id, fixture_id, and name
                return [...prevSelected, {
                    id: team.id,
                    fixture_id: team.fixture_id, // Store fixture_id
                    name: team.name // Keep name for display purposes
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
        const fixtureId = game.fixture_id; // Get fixture_id from the game

        if (fixtureId && gradeData[fixtureId]) {
            const gradeName = gradeData[fixtureId].name || `Grade ${fixtureId}`;
            // Remove year suffix if present (e.g., " - 2024")
            return gradeName.replace(/ - \d{4}$/, "");
        }

        // Fallback if fixtureId is missing or not in gradeData
        return `Unknown Competition`;
    };

    // Get opponent team for a Mentone game
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
            timeZone: 'UTC' // Keep UTC for consistency unless local time is required
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
            timeZone: 'UTC' // Keep UTC for consistency
        });
    };

    // Group games by date
    const groupGamesByDate = () => {
        const grouped = {};
        filteredGames.forEach(game => {
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
        if (filteredGames.length === 0) return "<p>No upcoming games found for the selected criteria.</p>";

        const grouped = groupGamesByDate();
        let html = `<div style="font-family: Arial, sans-serif; max-width: 100%;">
            <h2 style="text-align: center; color: #1B1F4A; margin-bottom: 20px;">MENTONE HOCKEY CLUB - UPCOMING GAMES (${getFilterDateRangeText(dateFilter)})</h2>`;

        Object.entries(grouped).forEach(([date, dateGames]) => {
            html += `<h3 style="text-align: center; color: #1B1F4A; margin-top: 30px; margin-bottom: 10px; border-bottom: 1px solid #ddd; padding-bottom: 5px;">${date}</h3>`;
            html += `
            <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px;">
                <tr style="background-color: #f2f2f2;">
                    <th style="padding: 8px; text-align: left; border-bottom: 1px solid #ddd;">Time</th>
                    <th style="padding: 8px; text-align: left; border-bottom: 1px solid #ddd;">Competition</th>
                    <th style="padding: 8px; text-align: left; border-bottom: 1px solid #ddd;">Playing</th>
                    <th style="padding: 8px; text-align: left; border-bottom: 1px solid #ddd;">Venue</th>
                </tr>`;

            dateGames.forEach((game, index) => {
                const time = formatGameTime(game.date);
                const opponent = getOpponentTeam(game);
                const opponentName = opponent?.name?.replace(" Hockey Club", "") || "TBD";
                const competition = getCompetitionName(game);
                const venue = game.venue || "Venue TBD";

                const rowStyle = index % 2 === 0 ? "" : "background-color: #f9f9f9;";

                html += `
                <tr style="${rowStyle}">
                    <td style="padding: 8px; text-align: left; border-bottom: 1px solid #ddd;">${time}</td>
                    <td style="padding: 8px; text-align: left; border-bottom: 1px solid #ddd;">${competition}</td>
                    <td style="padding: 8px; text-align: left; border-bottom: 1px solid #ddd;">${opponentName}</td>
                    <td style="padding: 8px; text-align: left; border-bottom: 1px solid #ddd;">${venue}</td>
                </tr>`;
            });

            html += '</table>';
        });

        html += '</div>';
        return html;
    };

    // Copy HTML to clipboard
    const copyHTMLToClipboard = () => {
        if (tableContainerRef.current) { // Ensure ref is available if using it
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
                document.execCommand('copy'); // Use deprecated for robustness
                setTextCopied(true);
                setTimeout(() => setTextCopied(false), 2000);
            } catch (err) {
                console.error("Failed to copy HTML table:", err);
                // Optionally show an error message to the user
            } finally {
                selection.removeAllRanges();
                document.body.removeChild(tempEl);
            }
        } else {
            console.error("Table container ref not found for copying.");
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
                {/* Optional: Add a retry button */}
            </div>
        );
    }

    // Prepare data for rendering
    const groupedGames = groupGamesByDate();
    const teamsByType = mentoneTeams.reduce((acc, team) => {
        const type = team.type || "Other";
        if (!acc[type]) acc[type] = [];
        acc[type].push(team);
        return acc;
    }, {});

    // --- RENDER SECTION ---
    return (
        <div className="bg-white rounded-xl shadow-sm overflow-hidden">
            {/* Header section */}
            <div className="bg-gradient-to-r from-mentone-navy to-mentone-navy/90 p-5 flex justify-between items-center">
                <h2 className="text-2xl font-bold text-mentone-gold tracking-tight">Upcoming Games</h2>
                <div className="bg-mentone-navy/50 backdrop-blur-sm rounded-lg p-1 flex">
                    {/* Date filter buttons */}
                    {[ { value: "thisWeek", label: "This Round" }, { value: "nextWeek", label: "Next Round" }, { value: "twoWeeks", label: "Two Rounds" }
                    ].map((filter) => ( <button key={filter.value} onClick={() => setDateFilter(filter.value)} className={`px-4 py-2 text-sm font-medium rounded-md transition-all ${ dateFilter === filter.value ? "bg-mentone-skyblue text-white shadow-sm" : "text-white/80 hover:bg-mentone-navy/70 hover:text-white" }`} > {filter.label} </button> ))}
                </div>
            </div>

            {/* Controls: Date range, Team filter, View switcher */}
            <div className="bg-mentone-navy/5 px-5 py-2 border-b border-gray-100 flex justify-between items-center">
                <div className="flex items-center gap-3">
                    {/* Date Range Display */}
                    <p className="text-mentone-navy text-sm font-medium">
                        Showing games: {getFilterDateRangeText(dateFilter)}
                    </p>

                    {/* Team filter dropdown */}
                    <div className="relative">
                        <button onClick={() => setTeamFilterOpen(!teamFilterOpen)} className={`flex items-center gap-2 text-sm px-3 py-1.5 rounded-lg border transition-colors ${ selectedTeams.length > 0 ? "bg-mentone-skyblue text-white border-mentone-skyblue" : "bg-white text-mentone-navy border-gray-300 hover:border-mentone-skyblue" }`} >
                            {/* Filter Icon & Text */}
                            <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z" /></svg>
                            {selectedTeams.length === 0 ? <span>Filter Teams</span> : <span>{selectedTeams.length} team{selectedTeams.length !== 1 ? 's' : ''} selected</span>}
                            <svg xmlns="http://www.w3.org/2000/svg" className={`h-4 w-4 transition-transform ${teamFilterOpen ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" /></svg>
                        </button>

                        {/* Dropdown Content */}
                        {teamFilterOpen && (
                            <div className="absolute z-20 top-full left-0 mt-1 bg-white border border-gray-200 rounded-lg shadow-lg w-72 max-h-96 overflow-y-auto">
                                {/* Dropdown Header */}
                                <div className="sticky top-0 bg-white px-4 py-2 border-b border-gray-100 flex justify-between items-center">
                                    <h3 className="text-sm font-semibold text-mentone-navy">Filter by team</h3>
                                    <button onClick={clearTeamSelections} className="text-xs text-mentone-skyblue hover:text-mentone-navy" > Clear all </button>
                                </div>
                                {/* Dropdown Body */}
                                <div className="p-2">
                                    {mentoneTeams.length === 0 ? (
                                        <div className="py-3 px-2 text-sm text-gray-500 text-center"> Loading teams... </div>
                                    ) : (
                                        Object.entries(teamsByType).map(([type, typeTeams]) => (
                                            <div key={type} className="mb-3">
                                                <h4 className="text-xs font-bold px-2 py-1 bg-gray-100 rounded-md text-mentone-navy mb-1">{type}</h4>
                                                <div className="space-y-1">
                                                    {typeTeams.map(team => {
                                                        const compName = team.name.includes(" - ") ? team.name.split(" - ")[1] : team.name;
                                                        const isSelected = selectedTeams.some(t => t.id === team.id);
                                                        // Disable checkbox if team lacks fixture_id needed for filtering
                                                        const isDisabled = !team.fixture_id;
                                                        return (
                                                            <div key={team.id} className={`flex items-center pl-2 ${isDisabled ? 'opacity-50 cursor-not-allowed' : ''}`}>
                                                                <input
                                                                    type="checkbox"
                                                                    id={`team-${team.id}`}
                                                                    checked={isSelected}
                                                                    onChange={() => toggleTeamSelection(team)}
                                                                    disabled={isDisabled} // Disable if no fixture_id
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

                {/* View mode toggle */}
                <div className="flex items-center bg-white border border-gray-200 rounded-lg overflow-hidden">
                    {/* Card/Table buttons */}
                    <button onClick={() => setViewMode("cards")} className={`px-3 py-1.5 text-sm font-medium flex items-center ${ viewMode === "cards" ? "bg-mentone-skyblue text-white" : "text-gray-700 hover:bg-gray-100" }`} > <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor"> <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" /> </svg> Cards </button>
                    <button onClick={() => setViewMode("table")} className={`px-3 py-1.5 text-sm font-medium flex items-center ${ viewMode === "table" ? "bg-mentone-skyblue text-white" : "text-gray-700 hover:bg-gray-100" }`} > <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor"> <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 10h18M3 14h18m-9-4v8m-7 0h14a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" /> </svg> Table </button>
                </div>
            </div>

            {/* Show active filters if teams are selected */}
            {selectedTeams.length > 0 && (
                <div className="bg-mentone-skyblue/5 px-5 py-2 border-b border-mentone-skyblue/10">
                    {/* Active filter badges */}
                    <div className="flex flex-wrap items-center gap-2"> <span className="text-xs font-medium text-mentone-navy">Active filters:</span> {selectedTeams.map(team => { const compName = team.name.includes(" - ") ? team.name.split(" - ")[1] : team.name; return ( <div key={team.id} className="bg-mentone-skyblue/10 text-mentone-skyblue text-xs px-2 py-1 rounded-full flex items-center" > <span className="mr-1">{compName}</span> <button onClick={() => toggleTeamSelection(team)} className="hover:text-mentone-navy" title={`Remove ${compName} filter`} > <svg xmlns="http://www.w3.org/2000/svg" className="h-3 w-3" viewBox="0 0 20 20" fill="currentColor"> <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" /> </svg> </button> </div> ); })} <button onClick={clearTeamSelections} className="text-xs text-mentone-skyblue hover:text-mentone-navy ml-1" > Clear all </button> </div>
                </div>
            )}

            {/* Game listings - Card View */}
            {viewMode === "cards" && (
                <div className="p-5">
                    {filteredGames.length === 0 ? (
                        <div className="flex flex-col items-center justify-center py-16 bg-gray-50 rounded-lg border border-gray-100"> <svg xmlns="http://www.w3.org/2000/svg" className="h-12 w-12 text-gray-300 mb-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"> <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" /> </svg> <p className="text-gray-500 font-medium">No upcoming games found</p> <p className="text-gray-400 text-sm mt-1"> {selectedTeams.length > 0 ? "Try selecting different teams or date range" : "Try selecting a different time period"} </p> </div>
                    ) : (
                        <div className="space-y-8">
                            {Object.entries(groupedGames).map(([date, dateGames]) => (
                                <div key={date} className="relative">
                                    {/* Sticky Date Header */}
                                    <div className="sticky top-0 bg-white z-10 pt-1 pb-3"> <h3 className="inline-block px-4 py-1.5 bg-mentone-gold/10 text-mentone-navy font-bold rounded-full text-sm"> {date} </h3> </div>
                                    {/* Game Cards for the Date */}
                                    <div className="space-y-4">
                                        {dateGames.map((game) => {
                                            // Check if Mentone is home or away
                                            const isMentoneHome = game.home_team?.club?.toLowerCase() === "mentone";
                                            const isMentoneAway = game.away_team?.club?.toLowerCase() === "mentone";
                                            // Get opponent team
                                            const opponentTeam = getOpponentTeam(game);
                                            const opponentName = opponentTeam?.name?.replace(" Hockey Club", "") || "TBD";
                                            const competitionName = getCompetitionName(game);

                                            return (
                                                <div key={game.id} className="bg-white border border-gray-100 rounded-xl overflow-hidden shadow-sm hover:shadow-md transition-shadow duration-300 transform hover:translate-y-[-2px]" >
                                                    {/* Card Header: Competition & Round */}
                                                    <div className="bg-gray-50 px-4 py-2 border-b border-gray-100 flex justify-between items-center">
                                                        <div className="flex items-center">
                                                            <span className="font-semibold text-mentone-navy"> {competitionName} </span>
                                                        </div>
                                                        <div className="flex items-center space-x-2">
                                                            {game.round && (
                                                                <span className="text-xs px-2 py-0.5 bg-mentone-gold/80 text-mentone-navy rounded-full font-medium">
                                                                    Round {game.round}
                                                                </span>
                                                            )}
                                                        </div>
                                                    </div>
                                                    {/* Card Body: Teams & Info */}
                                                    <div className="p-4">
                                                        {/* Teams Row */}
                                                        <div className="flex items-center justify-between mb-5">
                                                            <div className="flex flex-col items-center w-5/12">
                                                                <span className={`text-center font-medium ${isMentoneHome ? "text-mentone-skyblue" : "text-gray-700"}`}>
                                                                    {isMentoneHome ? "Mentone" : game.home_team?.name?.replace(" Hockey Club", "") || "TBD"}
                                                                </span>
                                                            </div>
                                                            <div className="flex flex-col items-center justify-center">
                                                                <span className="text-gray-400 text-sm font-medium">vs</span>
                                                            </div>
                                                            <div className="flex flex-col items-center w-5/12">
                                                                <span className={`text-center font-medium ${isMentoneAway ? "text-mentone-skyblue" : "text-gray-700"}`}>
                                                                    {isMentoneAway ? "Mentone" : game.away_team?.name?.replace(" Hockey Club", "") || "TBD"}
                                                                </span>
                                                            </div>
                                                        </div>
                                                        {/* Info Row: Time & Venue */}
                                                        <div className="flex justify-between items-center pt-3 border-t border-gray-100">
                                                            <div className="flex items-center text-gray-600">
                                                                <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                                                                </svg>
                                                                <span className="text-sm">{formatGameTime(game.date)}</span>
                                                            </div>
                                                            <div className="flex items-center text-gray-600 min-w-0">
                                                                <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 mr-1 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
                                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
                                                                </svg>
                                                                <span className="text-sm truncate">{game.venue || "Venue TBD"}</span>
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

            {/* Compact Game listings - Table View */}
            {viewMode === "table" && (
                <div className="p-3">
                    {filteredGames.length === 0 ? (
                        <div className="flex flex-col items-center justify-center py-8 bg-gray-50 rounded border border-gray-100">
                            <svg xmlns="http://www.w3.org/2000/svg" className="h-10 w-10 text-gray-300 mb-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
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
                                    className={`px-3 py-1 rounded text-white text-xs flex items-center ${textCopied ? 'bg-green-600' : 'bg-mentone-skyblue hover:bg-mentone-skyblue/90'} transition-colors`}
                                >
                                    {textCopied ? (
                                        <>✓ Copied!</>
                                    ) : (
                                        <>⧉ Copy HTML</>
                                    )}
                                </button>
                            </div>

                            {/* Table Display */}
                            <div ref={tableContainerRef} className="overflow-auto bg-white rounded border border-gray-200">
                                {Object.entries(groupedGames).map(([date, dateGames]) => (
                                    <div key={date} className="mb-4">
                                        <h3 className="text-md font-semibold text-mentone-navy mb-2 border-b px-2 py-1 bg-gray-100">{date}</h3>
                                        <table className="min-w-full divide-y divide-gray-200 text-xs">
                                            <thead className="bg-gray-50">
                                            <tr>
                                                <th className="px-2 py-1 text-center font-medium text-gray-500 uppercase">Time</th>
                                                <th className="px-2 py-1 text-center font-medium text-gray-500 uppercase">Competition</th>
                                                <th className="px-2 py-1 text-center font-medium text-gray-500 uppercase">Opponent</th>
                                                <th className="px-2 py-1 text-center font-medium text-gray-500 uppercase">Venue</th>
                                            </tr>
                                            </thead>
                                            <tbody className="divide-y divide-gray-100">
                                            {dateGames.map((game, index) => {
                                                const opponentTeam = getOpponentTeam(game);
                                                const opponentName = opponentTeam?.name?.replace(" Hockey Club", "") ||
                                                    opponentTeam?.club?.replace(" Hockey Club", "") ||
                                                    "TBD";
                                                const competitionName = getCompetitionName(game);

                                                return (
                                                    <tr key={game.id} className={index % 2 === 0 ? 'bg-white' : 'bg-gray-50'}>
                                                        <td className="px-2 py-1 text-center text-gray-600 whitespace-nowrap">
                                                            {formatGameTime(game.date)}
                                                        </td>
                                                        <td className="px-2 py-1 text-center text-gray-800 whitespace-nowrap">
                                                            {competitionName}
                                                        </td>
                                                        <td className="px-2 py-1 text-center text-gray-800 whitespace-nowrap">
                                                            {opponentName}
                                                        </td>
                                                        <td className="px-2 py-1 text-center text-gray-600 whitespace-nowrap">
                                                            {(game.venue || "Venue TBD").trim()}
                                                        </td>
                                                    </tr>
                                                );
                                            })}
                                            </tbody>
                                        </table>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            )}

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