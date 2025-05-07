// src/components/TeamDetailPage.jsx
import React, { useState, useEffect, useCallback } from 'react';
import { useParams, Link } from 'react-router-dom';
import { doc, getDoc, collection, query, where, orderBy, getDocs } from "firebase/firestore";
import { db } from "../firebase";
import { ClipLoader } from 'react-spinners'; // Assuming you have this installed
import { useFavorites } from "../context/FavoritesContext";
import FavoriteButton from "./common/FavoriteButton";

// Base URL for your deployed API endpoint
const API_BASE_URL = 'https://ladder-api-55xtnu7seq-uc.a.run.app'; // <-- YOUR CLOUD RUN URL

// Helper function to format date (adjust timezone as needed)
const formatGameDate = (timestamp) => {
    if (!timestamp?.toDate) return "Date TBD";
    return timestamp.toDate().toLocaleDateString('en-AU', {
        weekday: 'short', day: 'numeric', month: 'short', year: 'numeric', timeZone: 'Australia/Melbourne'
    });
};

// Helper function to format time (adjust timezone as needed)
const formatGameTime = (timestamp) => {
    if (!timestamp?.toDate) return "Time TBD";
    return timestamp.toDate().toLocaleTimeString('en-AU', {
        hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'Australia/Melbourne'
    });
};

// Helper to determine game outcome and badge style
const getOutcomeBadge = (game, teamId) => {
    if (game.status !== 'completed' || typeof game.home_team?.score !== 'number' || typeof game.away_team?.score !== 'number') {
        return <span className="text-xs px-2 py-0.5 bg-gray-100 text-gray-600 rounded-full font-medium">{game.status === 'scheduled' ? 'Scheduled' : 'Pending'}</span>;
    }

    const homeScore = game.home_team.score;
    const awayScore = game.away_team.score;
    const isMentoneHome = game.home_team.id === teamId || game.home_team.club?.toLowerCase() === 'mentone'; // Check both ID and club name just in case

    let result = 'Draw';
    let bgColor = 'bg-yellow-100';
    let textColor = 'text-yellow-800';

    if ((isMentoneHome && homeScore > awayScore) || (!isMentoneHome && awayScore > homeScore)) {
        result = 'Win';
        bgColor = 'bg-green-100';
        textColor = 'text-green-800';
    } else if ((isMentoneHome && homeScore < awayScore) || (!isMentoneHome && awayScore < homeScore)) {
        result = 'Loss';
        bgColor = 'bg-red-100';
        textColor = 'text-red-800';
    }

    return <span className={`text-xs px-2 py-0.5 ${bgColor} ${textColor} rounded-full font-medium`}>{result}</span>;
};


const TeamDetailPage = () => {
    const { teamId } = useParams(); // Get teamId from URL

    // Team & Game Data State
    const [teamData, setTeamData] = useState(null);
    const [games, setGames] = useState([]);
    const [summaryStats, setSummaryStats] = useState({ w: 0, d: 0, l: 0 });
    const { isFavorite, toggleFavorite } = useFavorites();
    // Ladder State
    const [ladderData, setLadderData] = useState({ position: null, points: null, isLoading: false, error: null });

    // UI State
    const [loadingTeam, setLoadingTeam] = useState(true);
    const [loadingGames, setLoadingGames] = useState(false);
    const [error, setError] = useState(null);
    const [viewMode, setViewMode] = useState('fixtures'); // 'fixtures' or 'players'

    // --- Fetch Team Data ---
    useEffect(() => {
        const fetchTeam = async () => {
            if (!teamId) return;
            setLoadingTeam(true);
            setError(null);
            setTeamData(null); // Reset on ID change
            console.log(`Fetching team data for ID: ${teamId}`);
            try {
                const teamRef = doc(db, "teams", teamId);
                const teamSnap = await getDoc(teamRef);

                if (teamSnap.exists()) {
                    const data = teamSnap.data();
                    console.log("Team data found:", data);
                    setTeamData({ id: teamSnap.id, ...data });
                    // Trigger ladder fetch only if comp_id and fixture_id exist
                    if (data.comp_id && data.fixture_id) {
                        fetchLadderData(data.comp_id, data.fixture_id);
                    } else {
                        console.warn("Team data missing comp_id or fixture_id, cannot fetch ladder.");
                        setLadderData({ position: null, points: null, isLoading: false, error: "Missing IDs" });
                    }
                } else {
                    console.error(`Team not found with ID: ${teamId}`);
                    setError(`Team not found.`);
                    setTeamData(null);
                }
            } catch (err) {
                console.error("Error fetching team data:", err);
                setError("Failed to load team details. Please try again.");
                setTeamData(null);
            } finally {
                setLoadingTeam(false);
            }
        };

        fetchTeam();
    }, [teamId]); // Re-run if teamId changes

    // --- Fetch Ladder Data via API ---
    const fetchLadderData = useCallback(async (comp_id, fixture_id) => {
        setLadderData({ position: null, points: null, isLoading: true, error: null }); // Reset and set loading
        console.log(`Fetching ladder data via API for comp ${comp_id}, fixture ${fixture_id}`);

        try {
            const response = await fetch(`${API_BASE_URL}/ladder?comp_id=${comp_id}&fixture_id=${fixture_id}`);
            if (!response.ok) {
                let errorMsg = `Ladder API Error (${response.status})`;
                try { const errorData = await response.json(); errorMsg = errorData.error || errorMsg; } catch (e) { /* ignore */ }
                throw new Error(errorMsg);
            }
            const data = await response.json();
            setLadderData({
                position: data.position ?? null,
                points: data.points ?? null,
                isLoading: false,
                error: data.error ?? null
            });
        } catch (error) {
            console.error(`Error fetching ladder from API:`, error);
            setLadderData({ position: null, points: null, isLoading: false, error: error.message || "Failed to fetch" });
        }
    }, []); // useCallback with empty dependency array as it doesn't depend on component state directly


    // --- Fetch Games Data ---
    useEffect(() => {
        const fetchGames = async () => {
            if (!teamData?.fixture_id) return; // Need fixture_id

            setLoadingGames(true);
            setGames([]); // Reset games
            setSummaryStats({ w: 0, d: 0, l: 0 }); // Reset stats
            console.log(`Fetching games for fixture ID: ${teamData.fixture_id}`);

            try {
                const gamesQuery = query(
                    collection(db, "games"),
                    where("fixture_id", "==", teamData.fixture_id),
                    orderBy("date", "asc") // Show earliest first
                );
                const gamesSnapshot = await getDocs(gamesQuery);
                const gamesData = gamesSnapshot.docs.map(doc => ({ id: doc.id, ...doc.data() }));
                console.log(`Fetched ${gamesData.length} games.`);
                setGames(gamesData);
            } catch (err) {
                console.error("Error fetching games:", err);
                setError("Failed to load game schedule."); // Set error specific to games
            } finally {
                setLoadingGames(false);
            }
        };

        fetchGames();
    }, [teamData]); // Re-run if teamData changes (specifically fixture_id)


    // --- Calculate Summary Stats ---
    useEffect(() => {
        if (!games || games.length === 0) return;

        let wins = 0;
        let draws = 0;
        let losses = 0;

        games.forEach(game => {
            if (game.status !== 'completed' || typeof game.home_team?.score !== 'number' || typeof game.away_team?.score !== 'number') {
                return; // Skip non-completed or invalid score games
            }
            const homeScore = game.home_team.score;
            const awayScore = game.away_team.score;
            // Determine if the current team (teamData.id) was home or away
            // Using fixture_id comparison in team objects within the game might be unreliable if team IDs change across systems.
            // Relying on club name might be safer if consistent. Best is having the specific team ID stored in game.home_team.id / game.away_team.id
            // Let's assume teamData.id matches game.home_team.id or game.away_team.id
            const isCurrentTeamHome = game.home_team?.id === teamData?.id; // Check if *this specific team ID* is the home team ID in the game doc
            const isCurrentTeamAway = game.away_team?.id === teamData?.id;

            if (!isCurrentTeamHome && !isCurrentTeamAway) {
                // Fallback or warning if IDs don't match - maybe check club name
                console.warn(`Team ID ${teamData?.id} not found directly in game ${game.id}. Checking club names.`);
                const isHomeClub = game.home_team?.club?.toLowerCase() === 'mentone';
                const isAwayClub = game.away_team?.club?.toLowerCase() === 'mentone';
                if(isHomeClub){
                    if (homeScore > awayScore) wins++;
                    else if (homeScore === awayScore) draws++;
                    else losses++;
                } else if(isAwayClub){
                    if (awayScore > homeScore) wins++;
                    else if (homeScore === awayScore) draws++;
                    else losses++;
                } else {
                    console.error(`Could not determine W/D/L for game ${game.id} for team ${teamData?.id}`)
                }

            } else {
                // IDs matched
                if (isCurrentTeamHome) {
                    if (homeScore > awayScore) wins++;
                    else if (homeScore === awayScore) draws++;
                    else losses++;
                } else { // isCurrentTeamAway
                    if (awayScore > homeScore) wins++;
                    else if (homeScore === awayScore) draws++;
                    else losses++;
                }
            }
        });

        setSummaryStats({ w: wins, d: draws, l: losses });
    }, [games, teamData]); // Recalculate if games or teamData changes


    // --- Render Logic ---

    if (loadingTeam) {
        return (
            <div className="flex items-center justify-center h-80 bg-white rounded-xl shadow-sm">
                <ClipLoader color="#4A90E2" loading={true} size={50} />
                <p className="ml-4 text-mentone-navy font-medium">Loading team details...</p>
            </div>
        );
    }

    if (error) {
        return (
            <div className="bg-red-50 border border-red-200 rounded-xl p-6 text-red-600 text-center">
                <p className="font-bold text-lg mb-2">Error Loading Team</p>
                <p className="text-md">{error}</p>
                <Link to="/teams" className="mt-4 inline-block px-4 py-2 bg-mentone-navy text-white rounded hover:bg-mentone-navy/90">Back to Teams</Link>
            </div>
        );
    }

    if (!teamData) {
        // Should be caught by error state, but as a fallback
        return <div className="bg-yellow-50 border border-yellow-200 rounded-xl p-5 text-yellow-700">Team data could not be loaded.</div>;
    }

    // Simplify competition name
    const competitionShortName = teamData.comp_name?.split(" - ")[0] || "Unknown Competition";
    const seasonYear = teamData.comp_name?.split(" - ")[1] || teamData.season || new Date().getFullYear();

    return (
        <div className="bg-white rounded-xl shadow-sm overflow-hidden">
            {/* Header */}
            <div className="bg-gradient-to-r from-mentone-navy to-mentone-navy/90 p-5 border-b border-mentone-navy/20">
                <div className="flex flex-col md:flex-row justify-between md:items-center gap-4">
                    <div>
                        <h2 className="text-2xl font-bold text-mentone-gold tracking-tight mb-1">{teamData.name}</h2>
                        <p className="text-mentone-skyblue text-sm font-medium">{competitionShortName} ({seasonYear})</p>
                    </div>
                    {/* Action Buttons - Mimic HV */}
                    <div className="flex flex-wrap gap-2">
                        {/* Ladder Button - Link or fetch? Link for now */}
                        {teamData.comp_id && teamData.fixture_id && (
                            <a
                                href={`https://www.hockeyvictoria.org.au/pointscore/${teamData.comp_id}/${teamData.fixture_id}`}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="px-3 py-1.5 bg-white/10 text-white text-xs font-medium rounded hover:bg-white/20 transition-colors backdrop-blur-sm border border-white/20"
                            >
                                View Official Ladder
                            </a>
                        )}
                        {/* Stats Button - Link to performance page? */}
                        <Link
                            to="/performance" // Link to your performance summary page
                            state={{ preSelectedFixtureId: teamData.fixture_id }} // Optional: pass state to pre-select team
                            className="px-3 py-1.5 bg-white/10 text-white text-xs font-medium rounded hover:bg-white/20 transition-colors backdrop-blur-sm border border-white/20"
                        >
                            View Club Stats
                        </Link>
                        {/* Export Buttons - Placeholder/Future */}
                        {/* <button className="px-3 py-1.5 bg-white/10 text-white text-xs font-medium rounded hover:bg-white/20 transition-colors backdrop-blur-sm border border-white/20">Export</button> */}
                    </div>
                </div>
            </div>

            {/* Summary Stats Bar */}
            <div className="p-4 border-b border-gray-100 bg-mentone-offwhite">
                <div className="grid grid-cols-3 md:grid-cols-5 gap-2 text-center">
                    <div className="p-2 bg-white rounded border border-gray-200">
                        <div className="text-xs text-gray-500 mb-1">Position</div>
                        <div className="text-xl font-bold text-mentone-navy">
                            {ladderData.isLoading ? <ClipLoader size={15} color="#1B1F4A"/> : ladderData.error ? '-' : ladderData.position ?? '-'}
                        </div>
                    </div>
                    <div className="p-2 bg-white rounded border border-gray-200">
                        <div className="text-xs text-gray-500 mb-1">Points</div>
                        <div className="text-xl font-bold text-mentone-navy">
                            {ladderData.isLoading ? <ClipLoader size={15} color="#1B1F4A"/> : ladderData.error ? '-' : ladderData.points ?? '-'}
                        </div>
                    </div>
                    <div className="p-2 bg-white rounded border border-gray-200">
                        <div className="text-xs text-green-600 mb-1">Wins</div>
                        <div className="text-xl font-bold text-green-700">{summaryStats.w}</div>
                    </div>
                    <div className="p-2 bg-white rounded border border-gray-200">
                        <div className="text-xs text-yellow-600 mb-1">Draws</div>
                        <div className="text-xl font-bold text-yellow-700">{summaryStats.d}</div>
                    </div>
                    <div className="p-2 bg-white rounded border border-gray-200">
                        <div className="text-xs text-red-600 mb-1">Losses</div>
                        <div className="text-xl font-bold text-red-700">{summaryStats.l}</div>
                    </div>
                </div>
            </div>

            {/* View Mode Toggle */}
            <div className="p-4 border-b border-gray-100 flex justify-center">
                <div className="inline-flex rounded-md shadow-sm bg-gray-100 p-1">
                    <button
                        onClick={() => setViewMode('fixtures')}
                        className={`px-6 py-2 text-sm font-medium rounded-md transition-colors ${viewMode === 'fixtures' ? 'bg-mentone-skyblue text-white shadow' : 'text-gray-700 hover:bg-white'}`}
                    >
                        Fixtures & Results
                    </button>
                    <button
                        onClick={() => setViewMode('players')}
                        className={`px-6 py-2 text-sm font-medium rounded-md transition-colors ${viewMode === 'players' ? 'bg-mentone-skyblue text-white shadow' : 'text-gray-700 hover:bg-white'}`}
                    >
                        Players
                    </button>
                </div>
            </div>

            {/* Content Area */}
            <div className="p-5 min-h-[300px]"> {/* Added min-height */}
                {viewMode === 'fixtures' && (
                    <>
                        {loadingGames && (
                            <div className="flex justify-center items-center h-40">
                                <ClipLoader color="#4A90E2" loading={true} size={40} />
                                <p className="ml-3 text-mentone-navy">Loading games...</p>
                            </div>
                        )}
                        {!loadingGames && games.length === 0 && (
                            <div className="text-center py-10 text-gray-500">
                                No games found for this team's current fixture.
                            </div>
                        )}
                        {!loadingGames && games.length > 0 && (
                            <div className="space-y-4">
                                {games.map(game => {
                                    const opponent = game.home_team?.club?.toLowerCase().includes("mentone") ? game.away_team : game.home_team;
                                    const isHome = game.home_team?.club?.toLowerCase().includes("mentone");
                                    const scoreDisplay = (game.status === 'completed' && typeof game.home_team?.score === 'number')
                                        ? `${game.home_team.score} - ${game.away_team.score}`
                                        : '-';

                                    return (
                                        <div key={game.id} className="bg-white border border-gray-100 rounded-lg shadow-sm hover:shadow-md transition-shadow">
                                            <div className="p-4 text-sm">
                                                <div className="grid grid-cols-1 md:grid-cols-12 gap-x-4 gap-y-2 items-center">
                                                    {/* Date & Round */}
                                                    <div className="md:col-span-3">
                                                        <div className="font-semibold text-mentone-navy">Round {game.round || '?'}</div>
                                                        <div className="text-gray-600">{formatGameDate(game.date)}</div>
                                                        <div className="text-gray-500">{formatGameTime(game.date)}</div>
                                                    </div>
                                                    {/* Venue */}
                                                    <div className="md:col-span-3">
                                                        <div className="font-medium text-gray-800 truncate" title={game.venue || 'Venue TBD'}>{game.venue || 'Venue TBD'}</div>
                                                        <div className="text-gray-500">{game.venue_short || ''}</div>
                                                    </div>
                                                    {/* Opponent & Score */}
                                                    <div className="md:col-span-4 text-center md:text-left">
                                                        <div className={`font-medium ${opponent?.club?.toLowerCase() === 'mentone' ? 'text-mentone-skyblue' : 'text-gray-800'}`}>{opponent?.name || 'Opponent TBD'}</div>
                                                        <div className="font-bold text-lg text-mentone-navy mt-1">{scoreDisplay}</div>
                                                    </div>
                                                    {/* Outcome & Details */}
                                                    <div className="md:col-span-2 flex flex-col items-center md:items-end gap-2">
                                                        {getOutcomeBadge(game, teamData.id)}
                                                        <a
                                                            href={game.url || '#'} // Link to HV game detail page if available
                                                            target="_blank"
                                                            rel="noopener noreferrer"
                                                            className={`mt-1 px-3 py-1 text-xs rounded border transition-colors ${game.url ? 'border-mentone-skyblue text-mentone-skyblue hover:bg-mentone-skyblue/10' : 'border-gray-300 text-gray-400 cursor-not-allowed'}`}
                                                            aria-disabled={!game.url}
                                                            onClick={(e) => !game.url && e.preventDefault()}
                                                        >
                                                            Details
                                                        </a>
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>
                        )}
                    </>
                )}

                {viewMode === 'players' && (
                    <div className="text-center py-16 bg-gray-50 rounded-lg border border-gray-100">
                        <svg xmlns="http://www.w3.org/2000/svg" className="h-12 w-12 text-gray-300 mx-auto mb-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
                        </svg>
                        <p className="text-gray-500 font-medium">Player Information</p>
                        <p className="text-gray-400 text-sm mt-1">This section will display the team's player list (coming soon).</p>
                        {/* Placeholder for future table/list */}
                    </div>
                )}
            </div>
        </div>
    );
};

export default TeamDetailPage;