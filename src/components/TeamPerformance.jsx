// src/components/TeamPerformance.jsx
import React, { useState, useEffect, useCallback, useRef } from 'react';
import { collection, query, where, getDocs, orderBy } from "firebase/firestore";
import { db } from "../firebase";
import { ClipLoader } from 'react-spinners';

// Base URL for your deployed API endpoint
const API_BASE_URL = 'https://ladder-api-55xtnu7seq-uc.a.run.app'; // <-- YOUR CLOUD RUN URL

const TeamPerformance = () => {
    // Core Data States
    const [allCompletedMentoneGames, setAllCompletedMentoneGames] = useState([]);
    const [teams, setTeams] = useState([]); // Stores { id: string, name: string, fixture_id: number, comp_id: number, type: string }

    // Frontend Cache/State for Ladder Data
    const [ladderCache, setLadderCache] = useState({});

    // UI/Selection States
    const [selectedFixtureIds, setSelectedFixtureIds] = useState([]); // Should store NUMBERS
    const [isTeamSelectorOpen, setIsTeamSelectorOpen] = useState(false);
    const selectorRef = useRef(null);

    // Combined Performance Stats State
    const [performanceStats, setPerformanceStats] = useState({ aggregate: {}, individual: {} });

    // Loading and Error States
    const [loadingTeams, setLoadingTeams] = useState(true);
    const [loadingGames, setLoadingGames] = useState(false);
    const [error, setError] = useState(null);

    // --- Fetch Teams ---
    useEffect(() => {
        const fetchTeams = async () => {
            setLoadingTeams(true);
            setError(null);
            try {
                console.log("Fetching Mentone teams for Performance...");
                const teamsQuery = query(
                    collection(db, "teams"),
                    where("is_home_club", "==", true),
                    // where("active", "==", true), // Keep this commented unless needed
                    orderBy("type"),
                    orderBy("name")
                );
                const snapshot = await getDocs(teamsQuery);
                const teamsData = snapshot.docs.map(doc => {
                    const data = doc.data();
                    // Ensure fixture_id and comp_id exist and are numbers after migration
                    if (typeof data.fixture_id !== 'number' || typeof data.comp_id !== 'number') {
                        console.warn(`Team "${data.name}" (ID: ${doc.id}) has invalid or missing fixture_id/comp_id types. Excluding. Fixture: ${data.fixture_id} (${typeof data.fixture_id}), Comp: ${data.comp_id} (${typeof data.comp_id})`);
                        return null;
                    }
                    return {
                        id: doc.id, // Keep doc ID as string
                        name: data.name,
                        fixture_id: data.fixture_id, // Should be number
                        comp_id: data.comp_id,       // Should be number
                        type: data.type,
                    };
                }).filter(Boolean); // Remove nulls

                console.log(`Fetched ${teamsData.length} valid Mentone teams for Performance.`);
                setTeams(teamsData);

            } catch (err) {
                if (err.code === 'failed-precondition') {
                    console.error("Firestore index required:", err.message);
                    setError("Database query requires an index. Please check the browser console F12 for a link to create it.");
                } else {
                    console.error("Error fetching teams:", err);
                    setError("Failed to load teams list.");
                }
            } finally {
                setLoadingTeams(false);
            }
        };
        fetchTeams();
    }, []);

    // --- DEBUG: Verify fixture_id type in teams state ---
    useEffect(() => {
        if (teams.length > 0) {
            console.log("[DEBUG] Teams state loaded. Checking fixture_id type of first team:", typeof teams[0].fixture_id, teams[0].fixture_id);
            // Also check a few more for consistency
            if (teams.length > 5) {
                console.log("[DEBUG] Checking fixture_id type of 5th team:", typeof teams[5].fixture_id, teams[5].fixture_id);
            }
        }
    }, [teams]);


    // --- Fetch All Completed Mentone Games ONCE ---
    useEffect(() => {
        const fetchAllGames = async () => {
            if (teams.length > 0 && allCompletedMentoneGames.length === 0 && !loadingTeams && !loadingGames) {
                setLoadingGames(true);
                setError(null);
                try {
                    console.log("Fetching all completed Mentone games for Performance...");
                    const gamesQuery = query(
                        collection(db, "games"),
                        where("mentone_playing", "==", true),
                        where("status", "==", "completed"),
                        orderBy("date", "desc")
                    );
                    const snapshot = await getDocs(gamesQuery);
                    // Ensure fixture_id in games is also a number
                    const gamesData = snapshot.docs.map(doc => {
                        const data = doc.data();
                        if (typeof data.fixture_id !== 'number') {
                            console.warn(`Game ${doc.id} has non-numeric fixture_id: ${data.fixture_id} (${typeof data.fixture_id}). Will be ignored by stats calc.`);
                        }
                        return { id: doc.id, ...data }
                    });
                    console.log(`Fetched ${gamesData.length} completed Mentone games for Performance.`);
                    setAllCompletedMentoneGames(gamesData);
                } catch (err) {
                    console.error("Error fetching completed games:", err);
                    setError("Failed to load game data.");
                    setAllCompletedMentoneGames([]);
                } finally {
                    setLoadingGames(false);
                }
            } else if (teams.length === 0 && !loadingTeams) {
                console.log("Skipping game fetch for Performance: No teams loaded.");
            }
        };
        fetchAllGames();
    }, [teams, loadingTeams, loadingGames]);

    // --- Fetch Ladder Data VIA API ---
    const fetchLadderDataFromAPI = useCallback(async (comp_id, fixture_id) => {
        // Ensure we use numeric fixture_id for cache key
        const numericFixtureId = Number(fixture_id);
        if (isNaN(numericFixtureId)) return; // Should not happen if teams state is correct

        if (ladderCache[numericFixtureId]?.isLoading) return;

        console.log(`Fetching ladder data via API for fixture ${numericFixtureId} from ${API_BASE_URL}`);
        setLadderCache(prev => ({
            ...prev,
            [numericFixtureId]: { ...prev[numericFixtureId], isLoading: true, error: null }
        }));

        try {
            const response = await fetch(`${API_BASE_URL}/ladder?comp_id=${comp_id}&fixture_id=${numericFixtureId}`); // Pass numeric IDs
            if (!response.ok) {
                let errorMsg = `Ladder API Error (${response.status})`;
                try { const errorData = await response.json(); errorMsg = errorData.error || errorMsg; } catch (e) { /* ignore */ }
                throw new Error(errorMsg);
            }
            const data = await response.json();
            setLadderCache(prev => ({
                ...prev,
                [numericFixtureId]: {
                    position: data.position ?? null,
                    points: data.points ?? null,
                    isLoading: false,
                    error: data.error ?? null
                }
            }));
        } catch (error) {
            console.error(`Error fetching ladder from API for ${numericFixtureId}:`, error);
            setLadderCache(prev => ({
                ...prev,
                [numericFixtureId]: { position: null, points: null, isLoading: false, error: error.message || "Fetch failed" }
            }));
        }
    }, [ladderCache]); // Dependency: ladderCache

    // --- Effect to Trigger Ladder Fetching for Selected Teams ---
    useEffect(() => {
        console.log("Performance: Checking which ladders to fetch via API for selections:", selectedFixtureIds);
        selectedFixtureIds.forEach(fixtureId => { // fixtureId here should be a number
            const team = teams.find(t => t.fixture_id === fixtureId); // Find team using the number

            const needsFetch = team && (
                !ladderCache[fixtureId] || // No cache entry
                (!ladderCache[fixtureId].isLoading && ladderCache[fixtureId].error !== null) || // Error exists
                (!ladderCache[fixtureId].isLoading && ladderCache[fixtureId].position === undefined) // No data yet
            );

            if (needsFetch) {
                console.log(`Performance: Triggering API ladder fetch for fixture ID: ${fixtureId} (Comp ID: ${team.comp_id})`);
                // Pass numeric IDs to API fetch function
                fetchLadderDataFromAPI(Number(team.comp_id), Number(team.fixture_id));
            } else if (!team) {
                console.warn(`Performance: Cannot fetch ladder for fixture ID ${fixtureId}: Team data not found.`);
                if (!ladderCache[fixtureId] || ladderCache[fixtureId]?.error !== "Team info missing") {
                    setLadderCache(prev => ({ ...prev, [fixtureId]: { position: null, points: null, isLoading: false, error: "Team info missing" }}));
                }
            }
        });
    }, [selectedFixtureIds, teams, ladderCache, fetchLadderDataFromAPI]);

    // --- Effect to Calculate Performance Stats ---
    useEffect(() => {
        // Guard Clauses
        if (teams.length === 0 || (allCompletedMentoneGames.length === 0 && !loadingGames)) {
            setPerformanceStats({ aggregate: { wins: 0, draws: 0, losses: 0, gf: 0, ga: 0, gd: 0, gamesPlayed: 0 }, individual: {} });
            return;
        }

        console.log("Performance: Recalculating stats for selections:", selectedFixtureIds);
        const individualStats = {}; // Use numeric fixture_id as key
        const aggregate = { wins: 0, draws: 0, losses: 0, gf: 0, ga: 0, gd: 0, gamesPlayed: 0 };

        // Initialize structure using numeric fixture_id from teams state
        teams.forEach(team => {
            // team.fixture_id should be a number here due to fetchTeams processing
            individualStats[team.fixture_id] = {
                teamName: team.name.replace(/Mentone Hockey Club - |Mentone - /g, ""),
                fixture_id: team.fixture_id, // Store the number
                wins: 0, draws: 0, losses: 0, gf: 0, ga: 0, gd: 0, gamesPlayed: 0,
                position: ladderCache[team.fixture_id]?.position ?? null,
                ladderPoints: ladderCache[team.fixture_id]?.points ?? null,
                ladderLoading: ladderCache[team.fixture_id]?.isLoading ?? false,
                ladderError: ladderCache[team.fixture_id]?.error ?? null,
            };
        });

        // Filter games where game.fixture_id is a number and is in selectedFixtureIds (which should also be numbers)
        const relevantGames = allCompletedMentoneGames.filter(game =>
            typeof game.fixture_id === 'number' && selectedFixtureIds.includes(game.fixture_id)
        );

        // Process relevant games
        relevantGames.forEach(game => {
            const fixtureId = game.fixture_id; // This is a number
            const stats = individualStats[fixtureId]; // Lookup using the number
            if (!stats) {
                console.warn(`Stats calc: Could not find individualStats entry for numeric fixtureId ${fixtureId} from game ${game.id}`);
                return;
            }

            const homeScore = game.home_team?.score; const awayScore = game.away_team?.score;
            if (typeof homeScore !== 'number' || typeof awayScore !== 'number') return; // Skip non-numeric scores

            const isMentoneHome = game.home_team?.club?.toLowerCase() === 'mentone';
            const goalsFor = isMentoneHome ? homeScore : awayScore;
            const goalsAgainst = isMentoneHome ? awayScore : homeScore;

            stats.gamesPlayed += 1; stats.gf += goalsFor; stats.ga += goalsAgainst;
            if (goalsFor > goalsAgainst) stats.wins += 1;
            else if (goalsFor === goalsAgainst) stats.draws += 1;
            else stats.losses += 1;
        });

        // Calculate GD and aggregate stats using numeric fixture IDs
        const finalIndividualStats = {};
        selectedFixtureIds.forEach(fixtureId => { // fixtureId from state should be a number
            console.log(`[DEBUG] Aggregating for selected fixtureId: ${fixtureId} (Type: ${typeof fixtureId})`); // Log selected ID and type
            // Check keys in individualStats (should be numbers)
            // console.log("[DEBUG] Keys in individualStats:", Object.keys(individualStats).map(k => `${k} (${typeof parseInt(k, 10)})`)); // Convert key back to number for typeof check if needed

            const stats = individualStats[fixtureId]; // Lookup using the number

            if (stats) {
                stats.gd = stats.gf - stats.ga;
                finalIndividualStats[fixtureId] = stats;

                aggregate.wins += stats.wins; aggregate.draws += stats.draws; aggregate.losses += stats.losses;
                aggregate.gf += stats.gf; aggregate.ga += stats.ga; aggregate.gamesPlayed += stats.gamesPlayed;
            } else {
                // This log should indicate if the lookup failed
                console.warn(`[DEBUG] AGGREGATION FAILED: No stats found for key ${fixtureId} in individualStats object.`);
            }
        });
        aggregate.gd = aggregate.gf - aggregate.ga;

        setPerformanceStats({ aggregate, individual: finalIndividualStats });
        console.log("Performance: Stats calculation complete. Aggregate:", aggregate); // Log the final aggregate

    }, [selectedFixtureIds, allCompletedMentoneGames, teams, ladderCache, loadingGames]);

    // --- Event Handlers ---
    const handleTeamSelectionChange = (fixtureId) => {
        // Ensure fixtureId is treated as a number
        const numericFixtureId = Number(fixtureId);
        if (isNaN(numericFixtureId)) {
            console.error("Invalid fixtureId passed to selection change:", fixtureId);
            return;
        }
        console.log(`[DEBUG] Toggling selection for numeric fixtureId: ${numericFixtureId}`);
        setSelectedFixtureIds(prev =>
            prev.includes(numericFixtureId)
                ? prev.filter(id => id !== numericFixtureId) // Filter out the number
                : [...prev, numericFixtureId] // Add the number
        );
    };

    const toggleSelectAll = () => {
        if (selectedFixtureIds.length === teams.length) {
            setSelectedFixtureIds([]);
            console.log("[DEBUG] Deselected all teams.");
        } else {
            // Ensure we map to numbers
            const allNumericFixtureIds = teams.map(t => Number(t.fixture_id)).filter(id => !isNaN(id));
            setSelectedFixtureIds(allNumericFixtureIds);
            console.log("[DEBUG] Selected all teams with numeric IDs:", allNumericFixtureIds);
        }
    };

    // Close dropdown when clicking outside
    useEffect(() => {
        const handleClickOutside = (event) => {
            if (selectorRef.current && !selectorRef.current.contains(event.target)) {
                setIsTeamSelectorOpen(false);
            }
        };
        document.addEventListener("mousedown", handleClickOutside);
        return () => document.removeEventListener("mousedown", handleClickOutside);
    }, []);

    // --- Render Logic ---
    const isLoading = loadingTeams || loadingGames;

    // Group teams by type for the selector dropdown
    const teamsByType = teams.reduce((acc, team) => {
        const type = team.type || "Other";
        if (!acc[type]) acc[type] = [];
        acc[type].push(team);
        return acc;
    }, {});

    // Sort individual stats for display
    const sortedIndividualStats = Object.values(performanceStats.individual)
        .sort((a, b) => a.teamName.localeCompare(b.teamName));

    // --- RENDER SECTION ---
    return (
        <div className="p-4 bg-white rounded-xl shadow-sm">
            {/* Header and Team Selector */}
            <div className="mb-6 flex flex-col sm:flex-row justify-between sm:items-center gap-4">
                <h2 className="text-xl font-bold text-mentone-navy">Club Performance Summary</h2>
                <div className="relative" ref={selectorRef}>
                    <button
                        onClick={() => setIsTeamSelectorOpen(!isTeamSelectorOpen)}
                        className={`flex items-center gap-2 text-sm px-4 py-2 rounded-lg border transition-colors w-full sm:w-auto justify-between ${
                            selectedFixtureIds.length > 0
                                ? "bg-mentone-skyblue text-white border-mentone-skyblue"
                                : "bg-white text-mentone-navy border-gray-300 hover:border-mentone-skyblue"
                        }`}
                        disabled={loadingTeams || teams.length === 0}
                    >
                        {/* Icon */}
                        <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}> <path strokeLinecap="round" strokeLinejoin="round" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" /> </svg>
                        {/* Text */}
                        <span className="flex-grow text-left">
                            {loadingTeams ? "Loading Teams..." :
                                teams.length === 0 ? "No Teams Found" :
                                    selectedFixtureIds.length === 0 ? "Select Teams" :
                                        selectedFixtureIds.length === teams.length ? "All Teams Selected" :
                                            `${selectedFixtureIds.length} Team${selectedFixtureIds.length !== 1 ? 's' : ''} Selected`}
                        </span>
                        {/* Arrow */}
                        <svg xmlns="http://www.w3.org/2000/svg" className={`h-4 w-4 transition-transform flex-shrink-0 ${isTeamSelectorOpen ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}> <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" /> </svg>
                    </button>
                    {/* Dropdown Content */}
                    {isTeamSelectorOpen && (
                        <div className="absolute z-30 top-full right-0 mt-1 bg-white border border-gray-200 rounded-lg shadow-lg w-72 max-h-96 overflow-y-auto">
                            <div className="sticky top-0 bg-white px-4 py-2 border-b border-gray-100 flex justify-between items-center z-10">
                                <h3 className="text-sm font-semibold text-mentone-navy">Select Teams</h3>
                                <button onClick={toggleSelectAll} className="text-xs text-mentone-skyblue hover:text-mentone-navy" > {selectedFixtureIds.length === teams.length ? "Deselect All" : "Select All"} </button>
                            </div>
                            <div className="p-2">
                                {Object.entries(teamsByType).sort(([typeA], [typeB]) => typeA.localeCompare(typeB))
                                    .map(([type, typeTeams]) => (
                                        <div key={type} className="mb-2">
                                            <h4 className="text-xs font-bold px-2 py-1 bg-gray-100 rounded text-mentone-navy mb-1">{type}</h4>
                                            {typeTeams.sort((a,b) => a.name.localeCompare(b.name))
                                                .map(team => (
                                                    <div key={team.id} className="flex items-center px-2 py-1 hover:bg-gray-50 rounded">
                                                        <input
                                                            type="checkbox"
                                                            id={`team-select-${team.id}`} // Use unique team.id for id attribute
                                                            // *** Ensure comparison uses number ***
                                                            checked={selectedFixtureIds.includes(Number(team.fixture_id))}
                                                            // *** Pass fixture_id to handler ***
                                                            onChange={() => handleTeamSelectionChange(team.fixture_id)}
                                                            className="h-4 w-4 text-mentone-skyblue rounded border-gray-300 focus:ring-mentone-skyblue focus:ring-offset-0"
                                                        />
                                                        <label htmlFor={`team-select-${team.id}`} className="ml-2 text-sm text-gray-700 cursor-pointer flex-grow">
                                                            {team.name.replace(/Mentone Hockey Club - |Mentone - /g, "")}
                                                        </label>
                                                    </div>
                                                ))}
                                        </div>
                                    ))}
                            </div>
                        </div>
                    )}
                </div>
            </div>

            {/* Loading State */}
            {isLoading && ( <div className="flex justify-center items-center h-64"> <ClipLoader color="#4A90E2" loading={isLoading} size={50} /> <span className="ml-4 text-mentone-navy">Loading core data...</span> </div> )}
            {/* Error State */}
            {!isLoading && error && ( <div className="text-red-600 bg-red-50 p-4 rounded border border-red-200"> <strong>Error:</strong> {error} </div> )}

            {/* Data Display Area */}
            {!isLoading && !error && (
                <>
                    {/* Aggregate Summary Cards */}
                    {selectedFixtureIds.length > 0 ? (
                        <div className="mb-8 grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 md:gap-4">
                            {/* Render stat cards using performanceStats.aggregate */}
                            <StatCard label="Games" value={performanceStats.aggregate.gamesPlayed} color="gray" />
                            <StatCard label="Wins" value={performanceStats.aggregate.wins} color="green" />
                            <StatCard label="Draws" value={performanceStats.aggregate.draws} color="yellow" />
                            <StatCard label="Losses" value={performanceStats.aggregate.losses} color="red" />
                            <StatCard label="Goals For" value={performanceStats.aggregate.gf} color="blue" />
                            <StatCard label="Goal Diff" value={performanceStats.aggregate.gd} color="purple" showSign={true} />
                        </div>
                    ) : (
                        // Show empty state or prompt if no teams are selected
                        !isLoading && teams.length > 0 && (
                            <div className="mb-8 text-center p-6 text-sm text-gray-500">Select teams to view aggregate stats.</div>
                        )
                    )}

                    {/* Individual Team Table */}
                    {selectedFixtureIds.length > 0 && sortedIndividualStats.length > 0 ? (
                        <div className="overflow-x-auto">
                            <h3 className="text-lg font-semibold text-mentone-navy mb-3">Individual Team Stats</h3>
                            {/* ... Table structure ... */}
                            <table className="min-w-full divide-y divide-gray-200 border border-gray-200 text-sm">
                                <thead className="bg-gray-50">
                                <tr>
                                    <th scope="col" className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Team</th>
                                    <th scope="col" className="w-12 px-1 py-2 text-center text-xs font-medium text-gray-500 uppercase tracking-wider" title="Position">Pos</th>
                                    <th scope="col" className="w-14 px-1 py-2 text-center text-xs font-medium text-gray-500 uppercase tracking-wider" title="Points">Pts (L)</th>
                                    <th scope="col" className="w-12 px-1 py-2 text-center text-xs font-medium text-gray-500 uppercase tracking-wider" title="Played">GP</th>
                                    <th scope="col" className="w-12 px-1 py-2 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">W</th>
                                    <th scope="col" className="w-12 px-1 py-2 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">D</th>
                                    <th scope="col" className="w-12 px-1 py-2 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">L</th>
                                    <th scope="col" className="w-12 px-1 py-2 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">GF</th>
                                    <th scope="col" className="w-12 px-1 py-2 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">GA</th>
                                    <th scope="col" className="w-12 px-1 py-2 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">GD</th>
                                </tr>
                                </thead>
                                <tbody className="bg-white divide-y divide-gray-200">
                                {sortedIndividualStats.map((stats) => (
                                    <tr key={stats.fixture_id} className="hover:bg-gray-50">
                                        <td className="px-4 py-2 whitespace-nowrap font-medium text-gray-900">{stats.teamName}</td>
                                        <td className="px-1 py-2 whitespace-nowrap text-center text-gray-600"> {stats.ladderLoading ? <ClipLoader size={12} color="#9ca3af"/> : stats.ladderError ? <span title={stats.ladderError} className="text-red-500 font-bold cursor-help">!</span> : stats.position ?? '-'} </td>
                                        <td className="px-1 py-2 whitespace-nowrap text-center font-semibold text-gray-700"> {stats.ladderLoading ? <ClipLoader size={12} color="#9ca3af"/> : stats.ladderError ? '-' : stats.ladderPoints ?? '-'} </td>
                                        <td className="px-1 py-2 whitespace-nowrap text-center text-gray-600">{stats.gamesPlayed}</td>
                                        <td className="px-1 py-2 whitespace-nowrap text-center text-green-600 font-medium">{stats.wins}</td>
                                        <td className="px-1 py-2 whitespace-nowrap text-center text-yellow-600 font-medium">{stats.draws}</td>
                                        <td className="px-1 py-2 whitespace-nowrap text-center text-red-600 font-medium">{stats.losses}</td>
                                        <td className="px-1 py-2 whitespace-nowrap text-center text-blue-600">{stats.gf}</td>
                                        <td className="px-1 py-2 whitespace-nowrap text-center text-gray-600">{stats.ga}</td>
                                        <td className="px-1 py-2 whitespace-nowrap text-center font-medium text-purple-600"> {stats.gd > 0 ? `+${stats.gd}` : stats.gd === 0 && stats.gamesPlayed > 0 ? '0' : stats.gd < 0 ? stats.gd : '-'} </td>
                                    </tr>
                                ))}
                                </tbody>
                            </table>
                        </div>
                    ) : !isLoading && selectedFixtureIds.length > 0 && sortedIndividualStats.length === 0 ? (
                        <div className="text-center p-6 bg-gray-50 rounded text-gray-600"> No completed game data found yet for the selected team(s). Check back later. </div>
                    ) : !isLoading && teams.length > 0 ? (
                        <div className="text-center p-6 bg-blue-50 rounded text-blue-700 border border-blue-100"> Select one or more teams using the button above to view performance stats. </div>
                    ) : null}
                </>
            )}
            {/* Message if no teams found at all */}
            {!isLoading && !error && teams.length === 0 && (
                <div className="text-center p-6 bg-yellow-50 rounded text-yellow-700 border border-yellow-100"> No active Mentone teams with necessary data (fixture_id, comp_id) were found in the database. </div>
            )}
        </div>
    );
};


// Simple Stat Card Component
const StatCard = ({ label, value, color, showSign = false }) => {
    const colors = {
        gray: { bg: 'bg-gray-100', border: 'border-gray-200', text: 'text-gray-800', labelText: 'text-gray-600' },
        green: { bg: 'bg-green-100', border: 'border-green-200', text: 'text-green-800', labelText: 'text-green-600' },
        yellow: { bg: 'bg-yellow-100', border: 'border-yellow-200', text: 'text-yellow-800', labelText: 'text-yellow-600' },
        red: { bg: 'bg-red-100', border: 'border-red-200', text: 'text-red-800', labelText: 'text-red-600' },
        blue: { bg: 'bg-blue-100', border: 'border-blue-200', text: 'text-blue-800', labelText: 'text-blue-600' },
        purple: { bg: 'bg-purple-100', border: 'border-purple-200', text: 'text-purple-800', labelText: 'text-purple-600' },
    };
    const selectedColor = colors[color] || colors.gray;
    // Ensure value is a number for display logic, default to 0 if null/undefined
    const numericValue = (typeof value === 'number' && !isNaN(value)) ? value : 0;
    const displayValue = showSign && numericValue > 0 ? `+${numericValue}` : numericValue;

    return (
        <div className={`${selectedColor.bg} p-3 rounded-lg text-center border ${selectedColor.border}`}>
            <div className={`text-xl font-bold ${selectedColor.text}`}>
                {displayValue}
            </div>
            <div className={`text-xs ${selectedColor.labelText}`}>{label}</div>
        </div>
    );
};

export default TeamPerformance;