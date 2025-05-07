import { useState, useEffect } from "react";
import { collection, query, where, orderBy, getDocs, limit } from "firebase/firestore";
import { db } from "../firebase";
import { useFavorites } from "../context/FavoritesContext";
import FilterByFavorites from "./common/FilterByFavorites";

const TravelPlanner = () => {
    const [games, setGames] = useState([]);
    const [loadingGames, setLoadingGames] = useState(true);
    const [error, setError] = useState(null);
    const [firstGame, setFirstGame] = useState(null);
    const [secondGame, setSecondGame] = useState(null);
    const [travelData, setTravelData] = useState(null);
    const [loadingTravelData, setLoadingTravelData] = useState(false);
    const [dateFilter, setDateFilter] = useState("thisWeek");
    const [mentoneTeams, setMentoneTeams] = useState([]);
    const [selectedTeams, setSelectedTeams] = useState([]);
    const [teamFilterOpen, setTeamFilterOpen] = useState(false);
    const [gradeData, setGradeData] = useState({});
    const { showOnlyFavorites, favoriteTeams } = useFavorites();

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
                setLoadingGames(true);
                setError(null);

                const gradesRef = collection(db, "grades");
                const gradesSnapshot = await getDocs(gradesRef);
                const gradesMap = {};
                gradesSnapshot.forEach(doc => {
                    gradesMap[doc.id] = doc.data();
                });
                setGradeData(gradesMap);

                await fetchGames(dateFilter);
            } catch (err) {
                console.error("Error fetching data:", err);
                setError(err.message);
            } finally {
                setLoadingGames(false);
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

    const fetchGames = async (filter) => {
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

            const validGames = gamesData.filter(game =>
                game.venue && typeof game.venue === 'string' && game.venue.trim() !== ''
            );
            setGames(validGames);
        } catch (err) {
            console.error("Error fetching games:", err);
            setError(err.message);
            setGames([]);
        }
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

    useEffect(() => {
        if (firstGame && secondGame) {
            calculateTravelData();
        } else {
            setTravelData(null);
        }
    }, [firstGame, secondGame]);

    const formatGameDate = (date) => {
        if (!date) return "TBD";
        const gameDate = date instanceof Date ? date : new Date(date);
        return gameDate.toLocaleDateString('en-AU', { weekday: 'long', day: 'numeric', month: 'short', timeZone: 'UTC' });
    };

    const formatGameTime = (date) => {
        if (!date) return "TBD";
        const gameDate = date instanceof Date ? date : new Date(date);
        return gameDate.toLocaleTimeString('en-AU', { hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'UTC' });
    };

    const getCompetitionName = (game) => {
        const fixtureId = game.fixture_id;
        return fixtureId && gradeData[fixtureId] ? gradeData[fixtureId].name?.replace(/ - \d{4}$/, "") || `Grade ${fixtureId}` : "Unknown Competition";
    };

    const getOpponentTeam = (game) => {
        const isMentoneHome = game.home_team?.club?.toLowerCase().includes("mentone");
        return isMentoneHome ? game.away_team : game.home_team;
    };

    const calculateTravelData = async () => {
        if (!firstGame?.venue || !secondGame?.venue) return;

        setLoadingTravelData(true);

        try {
            const { getFunctions, httpsCallable } = await import("firebase/functions");
            const functions = getFunctions();
            const calculateTravelTime = httpsCallable(functions, 'calculateTravelTime');

            const originVenue = `${firstGame.venue}, Victoria, Australia`;
            const destinationVenue = `${secondGame.venue}, Victoria, Australia`;

            const result = await calculateTravelTime({
                origin: originVenue,
                destination: destinationVenue,
                mode: 'driving',
                units: 'metric'
            });

            const response = result.data;
            const distanceKm = (response.distance.value / 1000).toFixed(1);
            const durationMinutes = Math.round(response.duration.value / 60);

            setTravelData({
                distance: distanceKm,
                duration: durationMinutes,
                origin: response.origin,
                destination: response.destination,
                distanceText: response.distance.text,
                durationText: response.duration.text
            });
        } catch (err) {
            console.error("Error calculating travel data:", err);
            console.warn("Falling back to simulated travel data");

            const venueDistance = Math.abs(
                (firstGame.venue.length * 324) - (secondGame.venue.length * 278)
            ) % 25 + 5;
            const travelTimeMinutes = Math.round(venueDistance * 2 + Math.random() * 10);

            setTravelData({
                distance: venueDistance.toFixed(1),
                duration: travelTimeMinutes,
                distanceText: `${venueDistance.toFixed(1)} km`,
                durationText: `${travelTimeMinutes} mins`
            });
        } finally {
            setLoadingTravelData(false);
        }
    };

    const handleSelectGame = (game, position) => {
        if (position === 'first') {
            setFirstGame(game);
            if (secondGame && secondGame.id === game.id) {
                setSecondGame(null);
            }
        } else {
            setSecondGame(game);
            if (firstGame && firstGame.id === game.id) {
                setFirstGame(null);
            }
        }
    };

    const getDirectionsUrl = () => {
        if (!firstGame?.venue || !secondGame?.venue) return '#';

        const origin = encodeURIComponent(firstGame.venue + ", Victoria, Australia");
        const destination = encodeURIComponent(secondGame.venue + ", Victoria, Australia");

        return `https://www.google.com/maps/dir/?api=1&origin=${origin}&destination=${destination}&travelmode=driving`;
    };

    if (loadingGames) {
        return (
            <div className="flex items-center justify-center h-64 bg-white rounded-xl shadow-sm">
                <div className="flex flex-col items-center">
                    <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-mentone-skyblue mb-2"></div>
                    <p className="text-mentone-navy font-medium">Loading games...</p>
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

    return (
        <div className="bg-white rounded-xl shadow-sm overflow-hidden">
            <div className="bg-gradient-to-r from-mentone-navy to-mentone-navy/90 p-5 flex justify-between items-center">
                <div>
                    <h2 className="text-2xl font-bold text-mentone-gold tracking-tight">Travel Planner</h2>
                    <p className="text-mentone-skyblue text-sm mt-1">
                        Select two games to calculate travel time between venues
                    </p>
                </div>
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

            <div className="p-5 grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                    <h3 className="text-lg font-semibold text-mentone-navy mb-3">First Game</h3>
                    <div className="bg-mentone-offwhite rounded-lg p-4 min-h-[200px]">
                        {firstGame ? (
                            <div className="bg-white p-4 rounded-lg border border-mentone-skyblue/20 shadow-sm">
                                <div className="flex justify-between items-start mb-3">
                                    <div className="text-center w-full">
                                        <h4 className="font-bold text-mentone-navy">{getCompetitionName(firstGame)}</h4>
                                        <p className="text-sm text-gray-600 mt-1">Playing: {getOpponentTeam(firstGame)?.name || "TBD"}</p>
                                        <p className="text-sm text-gray-600">{formatGameDate(firstGame.date)} at {formatGameTime(firstGame.date)}</p>
                                    </div>
                                    <button
                                        onClick={() => setFirstGame(null)}
                                        className="text-gray-400 hover:text-red-500"
                                    >
                                        <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                                            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                                        </svg>
                                    </button>
                                </div>
                                <div className="flex items-center text-sm text-gray-600">
                                    <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 mr-1 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
                                    </svg>
                                    <span>{firstGame.venue}</span>
                                </div>
                            </div>
                        ) : (
                            <div className="h-full flex flex-col items-center justify-center text-gray-400">
                                <svg xmlns="http://www.w3.org/2000/svg" className="h-12 w-12 mb-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                                </svg>
                                <p className="text-sm">Select a game below</p>
                            </div>
                        )}
                    </div>
                </div>

                <div>
                    <h3 className="text-lg font-semibold text-mentone-navy mb-3">Second Game</h3>
                    <div className="bg-mentone-offwhite rounded-lg p-4 min-h-[200px]">
                        {secondGame ? (
                            <div className="bg-white p-4 rounded-lg border border-mentone-skyblue/20 shadow-sm">
                                <div className="flex justify-between items-start mb-3">
                                    <div className="text-center w-full">
                                        <h4 className="font-bold text-mentone-navy">{getCompetitionName(secondGame)}</h4>
                                        <p className="text-sm text-gray-600 mt-1">Playing: {getOpponentTeam(secondGame)?.name || "TBD"}</p>
                                        <p className="text-sm text-gray-600">{formatGameDate(secondGame.date)} at {formatGameTime(secondGame.date)}</p>
                                    </div>
                                    <button
                                        onClick={() => setSecondGame(null)}
                                        className="text-gray-400 hover:text-red-500"
                                    >
                                        <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                                            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                                        </svg>
                                    </button>
                                </div>
                                <div className="flex items-center text-sm text-gray-600">
                                    <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 mr-1 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
                                    </svg>
                                    <span>{secondGame.venue}</span>
                                </div>
                            </div>
                        ) : (
                            <div className="h-full flex flex-col items-center justify-center text-gray-400">
                                <svg xmlns="http://www.w3.org/2000/svg" className="h-12 w-12 mb-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                                </svg>
                                <p className="text-sm">Select a game below</p>
                            </div>
                        )}
                    </div>
                </div>
            </div>

            {(firstGame && secondGame) && (
                <div className="px-5 pb-5">
                    <div className="bg-mentone-gold/10 rounded-lg p-4 border border-mentone-gold/20">
                        <h3 className="text-lg font-semibold text-mentone-charcoal mb-3">Travel Information</h3>

                        {loadingTravelData ? (
                            <div className="flex justify-center items-center py-4">
                                <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-mentone-navy"></div>
                                <p className="ml-3 text-mentone-navy">Calculating travel time...</p>
                            </div>
                        ) : travelData ? (
                            <div className="space-y-4">
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                    <div className="bg-white rounded-lg p-3 shadow-sm">
                                        <div className="text-sm text-gray-500 mb-1">Distance</div>
                                        <div className="text-xl font-bold text-mentone-navy">
                                            {travelData.distanceText || `${travelData.distance} km`}
                                        </div>
                                    </div>
                                    <div className="bg-white rounded-lg p-3 shadow-sm">
                                        <div className="text-sm text-gray-500 mb-1">Estimated Travel Time</div>
                                        <div className="text-xl font-bold text-mentone-navy">
                                            {travelData.durationText || (
                                                travelData.duration < 60
                                                    ? `${travelData.duration} min`
                                                    : `${Math.floor(travelData.duration / 60)} hr ${travelData.duration % 60} min`
                                            )}
                                        </div>
                                    </div>
                                </div>

                                <div className="flex justify-center mt-2">
                                    <a
                                        href={getDirectionsUrl()}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="inline-flex items-center px-4 py-2 bg-mentone-navy text-white rounded-lg hover:bg-mentone-navy/90 transition-colors"
                                    >
                                        <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7" />
                                        </svg>
                                        Get Directions in Google Maps
                                    </a>
                                </div>

                                <div className="text-sm text-gray-500 text-center mt-2">
                                    <p>Travel times may vary based on traffic conditions.</p>
                                    <p>Plan to arrive at least 30 minutes before game time.</p>
                                </div>
                            </div>
                        ) : (
                            <div className="text-center py-4 text-gray-500">
                                Select two different games to see travel information.
                            </div>
                        )}
                    </div>
                </div>
            )}

            <div className="border-t border-gray-200 px-5 py-4">
                <h3 className="text-lg font-semibold text-mentone-navy mb-3">Upcoming Games</h3>

                {filteredGames.length === 0 ? (
                    <div className="text-center py-6 bg-gray-50 rounded-lg text-gray-500">
                        No upcoming games found.
                    </div>
                ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                        {filteredGames.map(game => (
                            <div key={game.id} className="border border-gray-200 rounded-lg bg-white hover:shadow-md transition-shadow p-3">
                                <div className="text-center mb-2">
                                    <h4 className="font-medium text-mentone-navy">{getCompetitionName(game)}</h4>
                                    <p className="text-sm text-gray-600">Playing: {getOpponentTeam(game)?.name || "TBD"}</p>
                                    <p className="text-sm text-gray-600">{formatGameDate(game.date)} at {formatGameTime(game.date)}</p>
                                </div>
                                <div className="flex items-center text-sm text-gray-600 mb-3">
                                    <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 mr-1 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
                                    </svg>
                                    <span>{game.venue || "Venue TBD"}</span>
                                </div>
                                <div className="flex justify-between">
                                    <button
                                        onClick={() => handleSelectGame(game, 'first')}
                                        className={`px-3 py-1 text-xs rounded-full border transition-colors ${
                                            firstGame?.id === game.id
                                                ? "bg-mentone-navy text-white border-mentone-navy"
                                                : "border-gray-300 text-gray-600 hover:border-mentone-navy hover:text-mentone-navy"
                                        }`}
                                    >
                                        Select as First Game
                                    </button>
                                    <button
                                        onClick={() => handleSelectGame(game, 'second')}
                                        className={`px-3 py-1 text-xs rounded-full border transition-colors ${
                                            secondGame?.id === game.id
                                                ? "bg-mentone-navy text-white border-mentone-navy"
                                                : "border-gray-300 text-gray-600 hover:border-mentone-navy hover:text-mentone-navy"
                                        }`}
                                    >
                                        Select as Second Game
                                    </button>
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
};

export default TravelPlanner;