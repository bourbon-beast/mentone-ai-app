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

    const [mentoneTeams, setMentoneTeams] = useState([]);
    const [selectedTeams, setSelectedTeams] = useState([]);
    const [teamFilterOpen, setTeamFilterOpen] = useState(false);

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
                const teamsData = teamsSnapshot.docs.map(doc => ({
                    id: doc.id,
                    ...doc.data()
                }));
                setMentoneTeams(teamsData);
            } catch (err) {
                console.error("Error fetching Mentone teams:", err);
            }
        };
        fetchMentoneTeams();
    }, []);

    useEffect(() => {
        const fetchData = async () => {
            try {
                setLoading(true);
                setError(null);

                const gradesRef = collection(db, "grades");
                const gradesSnapshot = await getDocs(gradesRef);
                const gradesMap = {};
                gradesSnapshot.forEach(doc => {
                    gradesMap[doc.id] = doc.data();
                });
                setGradeData(gradesMap);

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

    const getRoundDateRange = (weekOffset = 0) => {
        const now = new Date();
        const currentDay = now.getDay();
        const daysToLastFriday = currentDay >= 5 ? currentDay - 5 : currentDay + 2;
        const lastFriday = new Date(now);
        lastFriday.setDate(now.getDate() - daysToLastFriday + (weekOffset * 7));
        lastFriday.setHours(0, 0, 0, 0);

        const nextThursday = new Date(lastFriday);
        nextThursday.setDate(lastFriday.getDate() + 6);
        nextThursday.setHours(23, 59, 59, 999);

        return { startDate: lastFriday, endDate: nextThursday };
    };

    const fetchUpcomingGames = async (filter) => {
        try {
            let dateRanges = [];
            if (filter === "thisWeek") {
                dateRanges.push(getRoundDateRange(0));
            } else if (filter === "nextWeek") {
                dateRanges.push(getRoundDateRange(1));
            } else if (filter === "twoWeeks") {
                dateRanges.push(getRoundDateRange(0), getRoundDateRange(1));
            } else if (filter === "threeWeeks") {
                dateRanges.push(getRoundDateRange(0), getRoundDateRange(1), getRoundDateRange(2));
            } else if (filter === "fourWeeks") {
                dateRanges.push(getRoundDateRange(0), getRoundDateRange(1), getRoundDateRange(2), getRoundDateRange(3));
            }

            const gamesData = [];
            for (const range of dateRanges) {
                const gamesQuery = query(
                    collection(db, "games"),
                    where("date", ">=", range.startDate),
                    where("date", "<=", range.endDate),
                    where("mentone_playing", "==", true),
                    orderBy("date", "asc"),
                    limit(100)
                );

                const querySnapshot = await getDocs(gamesQuery);
                const rangeGames = querySnapshot.docs.map(doc => {
                    const gameData = doc.data();
                    return {
                        id: doc.id,
                        ...gameData,
                        roundStartDate: range.startDate,
                        roundEndDate: range.endDate,
                        date: gameData.date?.toDate ? gameData.date.toDate() : gameData.date
                    };
                });
                gamesData.push(...rangeGames);
            }
            setGames(gamesData);
        } catch (err) {
            console.error("Error fetching upcoming games:", err);
            setError(err.message);
            setGames([]);
        }
    };

    const filteredGames = selectedTeams.length > 0
        ? games.filter(game => selectedTeams.some(selectedTeam => selectedTeam.fixture_id === game.fixture_id))
        : showOnlyFavorites
            ? games.filter(game => favoriteTeams.some(favTeam => favTeam.fixture_id === game.fixture_id))
            : games;

    const toggleTeamSelection = (team) => {
        if (!team.fixture_id) return;
        setSelectedTeams(prevSelected => {
            const isSelected = prevSelected.some(t => t.id === team.id);
            if (isSelected) {
                return prevSelected.filter(t => t.id !== team.id);
            } else {
                return [...prevSelected, { id: team.id, fixture_id: team.fixture_id, name: team.name }];
            }
        });
    };

    const clearTeamSelections = () => {
        setSelectedTeams([]);
    };

    const getFilterDateRangeText = (filter) => {
        let dateRanges = [];
        if (filter === "thisWeek") dateRanges.push(getRoundDateRange(0));
        else if (filter === "nextWeek") dateRanges.push(getRoundDateRange(1));
        else if (filter === "twoWeeks") dateRanges.push(getRoundDateRange(0), getRoundDateRange(1));
        else if (filter === "threeWeeks") dateRanges.push(getRoundDateRange(0), getRoundDateRange(1), getRoundDateRange(2));
        else if (filter === "fourWeeks") dateRanges.push(getRoundDateRange(0), getRoundDateRange(1), getRoundDateRange(2), getRoundDateRange(3));

        const formatDate = (date) => date.toLocaleDateString('en-AU', { day: 'numeric', month: 'short' });
        const start = formatDate(dateRanges[0].startDate);
        const end = formatDate(dateRanges[dateRanges.length - 1].endDate);
        return `${start} - ${end}`;
    };

    const getRoundDateRangeText = (startDate, endDate) => {
        const formatDate = (date) => date.toLocaleDateString('en-AU', { day: 'numeric', month: 'short' });
        return `${formatDate(startDate)} - ${formatDate(endDate)}`;
    };

    const getCompetitionName = (game) => {
        const fixtureId = game.fixture_id;
        return fixtureId && gradeData[fixtureId] ? gradeData[fixtureId].name?.replace(/ - \d{4}$/, "") || `Grade ${fixtureId}` : "Unknown Competition";
    };

    const getOpponentTeam = (game) => {
        const isMentoneHome = game.home_team?.club?.toLowerCase().includes("mentone");
        return isMentoneHome ? game.away_team : game.home_team;
    };

    const formatGameDate = (date) => {
        if (!date) return "TBD";
        const gameDate = date instanceof Date ? date : new Date(date);
        return gameDate.toLocaleDateString('en-AU', { weekday: 'long', day: 'numeric', month: 'short' });
    };

    const formatGameTime = (date) => {
        if (!date) return "TBD";
        const gameDate = date instanceof Date ? date : new Date(date);
        return gameDate.toLocaleTimeString('en-AU', { hour: '2-digit', minute: '2-digit', hour12: false });
    };

    const generateHTMLTable = (roundGames, roundRangeText) => {
        if (roundGames.length === 0) return "<p>No upcoming games found for this round.</p>";

        let html = `<div style="font-family: Arial, sans-serif; max-width: 100%;">
            <h2 style="text-align: center; color: #1B1F4A; margin-bottom: 20px;">MENTONE HOCKEY CLUB - UPCOMING GAMES (${roundRangeText})</h2>
            <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px;">
                <tr style="background-color: #f2f2f2;">
                    <th style="padding: 8px; text-align: left; border-bottom: 1px solid #ddd;">Date</th>
                    <th style="padding: 8px; text-align: left; border-bottom: 1px solid #ddd;">Time</th>
                    <th style="padding: 8px; text-align: left; border-bottom: 1px solid #ddd;">Competition</th>
                    <th style="padding: 8px; text-align: left; border-bottom: 1px solid #ddd;">Playing</th>
                    <th style="padding: 8px; text-align: left; border-bottom: 1px solid #ddd;">Venue</th>
                </tr>`;

        roundGames.forEach((game, index) => {
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

    const copyHTMLToClipboard = (roundGames, roundRangeText) => {
        const htmlContent = generateHTMLTable(roundGames, roundRangeText);
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
                <p className="font-medium mb-1">Error Loading Games</p>
                <p className="text-sm">{error}</p>
            </div>
        );
    }

    const teamsByType = mentoneTeams.reduce((acc, team) => {
        const type = team.type || "Other";
        if (!acc[type]) acc[type] = [];
        acc[type].push(team);
        return acc;
    }, {});

    const gamesByRound = filteredGames.reduce((acc, game) => {
        if (!game.roundStartDate || !game.roundEndDate) {
            console.warn(`Game ${game.id} missing round dates, skipping grouping:`, game);
            return acc;
        }
        const key = `${game.roundStartDate.getTime()}-${game.roundEndDate.getTime()}`;
        if (!acc[key]) {
            acc[key] = {
                startDate: game.roundStartDate,
                endDate: game.roundEndDate,
                games: []
            };
        }
        acc[key].games.push(game);
        return acc;
    }, {});

    const sortedRounds = Object.values(gamesByRound).sort((a, b) => a.startDate - b.startDate);

    return (
        <div className="bg-white rounded-xl shadow-sm overflow-hidden">
            <div className="bg-gradient-to-r from-mentone-navy to-mentone-navy/90 p-5 flex justify-between items-center">
                <h2 className="text-2xl font-bold text-mentone-gold tracking-tight">Upcoming fixtures</h2>
                <div className="bg-mentone-navy/50 backdrop-blur-sm rounded-lg p-1 flex">
                    {[
                        { value: "thisWeek", label: "This Round" },
                        { value: "nextWeek", label: "Next Round" },
                        { value: "twoWeeks", label: "Two Rounds" },
                        { value: "threeWeeks", label: "Three Rounds" },
                        { value: "fourWeeks", label: "Four Rounds" }
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

            <div className="bg-mentone-navy/5 px-5 py-2 border-b border-gray-100 flex justify-between items-center">
                <div className="flex items-center gap-3">
                    <p className="text-mentone-navy text-sm font-medium">
                        Showing games: {getFilterDateRangeText(dateFilter)}
                    </p>
                    <FilterByFavorites buttonSize="sm" variant="outline" />
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
                            {selectedTeams.length === 0 ? <span>Filter Teams</span> : <span>{selectedTeams.length} team{selectedTeams.length !== 1 ? 's' : ''} selected</span>}
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

            <div className="p-3 min-h-[400px] flex flex-col">
                {sortedRounds.length === 0 ? (
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
                    sortedRounds.map((round, roundIndex) => (
                        <div key={`${round.startDate.getTime()}-${round.endDate.getTime()}`} className="mb-6">
                            <div className="flex justify-between items-center mb-2">
                                <h3 className="text-lg font-semibold text-mentone-navy">
                                    {getRoundDateRangeText(round.startDate, round.endDate)}
                                </h3>
                                <button
                                    onClick={() => copyHTMLToClipboard(round.games, getRoundDateRangeText(round.startDate, round.endDate))}
                                    className={`px-3 py-1 rounded text-white text-xs flex items-center ${
                                        textCopied ? 'bg-green-600' : 'bg-mentone-skyblue hover:bg-mentone-skyblue/90'
                                    } transition-colors`}
                                >
                                    {textCopied ? <>✓ Copied!</> : <>⧉ Copy HTML</>}
                                </button>
                            </div>
                            <div ref={tableContainerRef} className="overflow-auto bg-white rounded border border-gray-200">
                                <table className="min-w-full divide-y divide-gray-200 text-xs">
                                    <thead className="bg-gray-50">
                                    <tr>
                                        <th className="px-2 py-1 text-left font-medium text-gray-500 uppercase">Date</th>
                                        <th className="px-2 py-1 text-left font-medium text-gray-500 uppercase">Time</th>
                                        <th className="px-2 py-1 text-left font-medium text-gray-500 uppercase">Competition</th>
                                        <th className="px-2 py-1 text-left font-medium text-gray-500 uppercase">Venue</th>
                                        <th className="px-2 py-1 text-left font-medium text-gray-500 uppercase">Versus</th>
                                    </tr>
                                    </thead>
                                    <tbody className="divide-y divide-gray-100">
                                    {round.games.map((game, index) => {
                                        const opponentTeam = getOpponentTeam(game);
                                        const opponentName = opponentTeam?.name?.replace(" Hockey Club", "") || opponentTeam?.club?.replace(" Hockey Club", "") || "TBD";
                                        const competitionName = getCompetitionName(game);
                                        return (
                                            <tr key={game.id} className={index % 2 === 0 ? 'bg-white' : 'bg-gray-50'}>
                                                <td className="px-2 py-1 text-left text-gray-600 whitespace-nowrap">{formatGameDate(game.date)}</td>
                                                <td className="px-2 py-1 text-left text-gray-600 whitespace-nowrap">{formatGameTime(game.date)}</td>
                                                <td className="px-2 py-1 text-left text-gray-800 whitespace-nowrap">{competitionName}</td>
                                                <td className="px-2 py-1 text-left text-gray-600 whitespace-nowrap">{(game.venue || "Venue TBD").trim()}</td>
                                                <td className="px-2 py-1 text-left text-gray-800 whitespace-nowrap">{opponentName}</td>

                                            </tr>
                                        );
                                    })}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    ))
                )}
            </div>

            {process.env.NODE_ENV === 'development' && (
                <div className="mt-4 p-2 border-t text-xs text-gray-500">
                    <p>Debug: {games.length} Mentone games fetched. {filteredGames.length} games shown after team filter. {selectedTeams.length} teams selected.</p>
                </div>
            )}
        </div>
    );
};

export default UpcomingGames;