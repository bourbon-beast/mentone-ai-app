import { useState, useEffect, useCallback } from 'react'; // Added useCallback
import { collection, query, where, getDocs, orderBy } from "firebase/firestore";
import { db } from "../firebase";
import { ClipLoader } from 'react-spinners';
import axios from 'axios'; // Using axios for requests, slightly cleaner syntax often
import { parse } from 'node-html-parser'; // Using node-html-parser for robust server/client parsing

const TeamPerformance = () => {
    // Core Data States
    const [allCompletedMentoneGames, setAllCompletedMentoneGames] = useState([]);
    const [teams, setTeams] = useState([]); // Stores { id, name, fixture_id, comp_id }
    const [ladderCache, setLadderCache] = useState({}); // Cache for { fixture_id: { position: number, points: number, isLoading: bool, error: string|null } }

    // UI/Selection States
    const [selectedFixtureIds, setSelectedFixtureIds] = useState([]); // Array for multi-select
    const [isTeamSelectorOpen, setIsTeamSelectorOpen] = useState(false);

    // Combined Performance Stats State
    const [performanceStats, setPerformanceStats] = useState({ aggregate: {}, individual: {} });

    // Loading and Error States
    const [loadingTeams, setLoadingTeams] = useState(true);
    const [loadingGames, setLoadingGames] = useState(false);
    const [error, setError] = useState(null); // General error

    // --- Fetch Teams (includes comp_id now) ---
    useEffect(() => {
        const fetchTeams = async () => {
            setLoadingTeams(true);
            setError(null);
            try {
                console.log("Fetching Mentone teams...");
                const teamsQuery = query(
                    collection(db, "teams"),
                    where("is_home_club", "==", true),
                    orderBy("type"),
                    orderBy("name")
                );
                const snapshot = await getDocs(teamsQuery);
                const teamsData = snapshot.docs.map(doc => {
                    const data = doc.data();
                    if (!data.fixture_id || !data.comp_id) { // Need both for ladder URL
                        console.warn(`Team "${data.name}" (ID: ${doc.id}) is missing fixture_id or comp_id and will be excluded.`);
                        return null;
                    }
                    return { id: doc.id, name: data.name, fixture_id: data.fixture_id, comp_id: data.comp_id };
                }).filter(Boolean); // Filter out nulls

                console.log(`Fetched ${teamsData.length} valid Mentone teams.`);
                setTeams(teamsData);
            } catch (err) {
                console.error("Error fetching teams:", err);
                setError("Failed to load teams list.");
            } finally {
                setLoadingTeams(false);
            }
        };
        fetchTeams();
    }, []);

    // --- Fetch All Completed Mentone Games ONCE ---
    useEffect(() => {
        const fetchAllGames = async () => {
            if (teams.length > 0 && allCompletedMentoneGames.length === 0) {
                setLoadingGames(true);
                setError(null);
                try {
                    console.log("Fetching all completed Mentone games...");
                    const gamesQuery = query(
                        collection(db, "games"),
                        where("mentone_playing", "==", true),
                        where("status", "==", "completed"),
                        orderBy("date", "asc")
                    );
                    const snapshot = await getDocs(gamesQuery);
                    const gamesData = snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() }));
                    console.log(`Fetched ${gamesData.length} completed Mentone games.`);
                    setAllCompletedMentoneGames(gamesData);
                } catch (err) {
                    console.error("Error fetching completed games:", err);
                    setError("Failed to load game data.");
                    setAllCompletedMentoneGames([]); // Clear on error
                } finally {
                    setLoadingGames(false);
                }
            } else if (teams.length === 0 && !loadingTeams) {
                console.log("Skipping game fetch: No teams loaded.");
            }
        };
        fetchAllGames();
    }, [teams, loadingTeams]); // Depend on teams and loadingTeams status

    // --- Function to Scrape Ladder Data ---
    const scrapeLadderData = useCallback(async (comp_id, fixture_id) => {
        // Check cache first
        if (ladderCache[fixture_id] && !ladderCache[fixture_id].error && !ladderCache[fixture_id].isLoading) {
            console.log(`Ladder data for ${fixture_id} already cached.`);
            return ladderCache[fixture_id]; // Return cached data
        }
        // Prevent re-fetching if already loading
        if (ladderCache[fixture_id]?.isLoading) {
            console.log(`Already fetching ladder data for ${fixture_id}.`);
            return null; // Indicate loading
        }


        const url = `https://www.hockeyvictoria.org.au/pointscore/${comp_id}/${fixture_id}`;
        console.log(`Scraping ladder data for fixture ${fixture_id} from ${url}`);

        // Set loading state in cache immediately
        setLadderCache(prev => ({
            ...prev,
            [fixture_id]: { ...prev[fixture_id], isLoading: true, error: null }
        }));


        try {
            // NOTE: Scraping directly from the client might face CORS issues.
            // This might need to be moved to a backend API/serverless function.
            // For now, attempting direct fetch (may work depending on HV config).
            const response = await axios.get(url, { timeout: 15000 }); // Use axios
            const root = parse(response.data); // Use node-html-parser

            const table = root.querySelector('table.table'); // Find the ladder table
            if (!table) throw new Error("Ladder table not found on page.");

            const rows = table.querySelectorAll('tbody tr');
            let foundData = null;

            for (const row of rows) {
                const cells = row.querySelectorAll('td');
                if (cells.length < 10) continue; // Need at least 10 columns for points

                const teamLink = cells[0]?.querySelector('a');
                const teamName = teamLink?.textContent.trim() ?? cells[0]?.textContent.trim() ?? '';
                const positionText = cells[0]?.textContent.trim().split('.')[0]; // Extract '6' from '6.'


                // Check if this row is for a Mentone team
                // Using includes("Mentone") is generally safer for scraping variations
                if (teamName.includes("Mentone")) {
                    const pointsText = cells[9]?.textContent.trim(); // Points are usually 10th column (index 9)
                    const position = parseInt(positionText, 10);
                    const points = parseInt(pointsText, 10);

                    if (!isNaN(position) && !isNaN(points)) {
                        foundData = { position, points, isLoading: false, error: null };
                        console.log(`Found Mentone ladder data for ${fixture_id}: Pos=${position}, Pts=${points}`);
                        break; // Found our team, stop searching rows
                    } else {
                        console.warn(`Could not parse position/points for ${teamName} in fixture ${fixture_id}: Pos='${positionText}', Pts='${pointsText}'`);
                        // Store error in cache if parsing failed for Mentone row
                        foundData = { position: null, points: null, isLoading: false, error: "Parsing Error" };
                        break;
                    }
                }
            }

            if (foundData) {
                // Update cache with successful data or parsing error
                setLadderCache(prev => ({ ...prev, [fixture_id]: foundData }));
                return foundData;
            } else {
                // Mentone team not found in the table for this fixture
                console.warn(`Mentone team not found in ladder table for fixture ${fixture_id}`);
                const notFoundData = { position: null, points: null, isLoading: false, error: "Team Not Found" };
                setLadderCache(prev => ({ ...prev, [fixture_id]: notFoundData }));
                return notFoundData;
            }

        } catch (error) {
            console.error(`Error scraping ladder for fixture ${fixture_id}:`, error);
            const errorData = { position: null, points: null, isLoading: false, error: error.message || "Scraping Failed" };
            setLadderCache(prev => ({ ...prev, [fixture_id]: errorData }));
            return errorData; // Return error state
        }
    }, [ladderCache]); // Depend on ladderCache to use the latest version

    // --- Effect to Trigger Ladder Fetching for Selected Teams ---
    useEffect(() => {
        console.log("Checking which ladders to fetch based on selections:", selectedFixtureIds);
        selectedFixtureIds.forEach(fixtureId => {
            const team = teams.find(t => t.fixture_id === fixtureId);
            // Check if data is needed (not cached, not loading, no error preventing fetch)
            if (team && (!ladderCache[fixtureId] || (!ladderCache[fixtureId].isLoading && ladderCache[fixtureId].error))) {
                console.log(`Triggering ladder fetch for needed fixture ID: ${fixtureId} (Comp ID: ${team.comp_id})`);
                scrapeLadderData(team.comp_id, fixtureId); // Fire and forget, scrapeLadderData updates state
            } else if (!team) {
                console.warn(`Cannot fetch ladder for fixture ID ${fixtureId}: Team data not found.`);
            } else {
                console.log(`Ladder data for ${fixtureId} is cached, loading, or has non-retryable error. Skipping fetch.`);
            }
        });
    }, [selectedFixtureIds, teams, ladderCache, scrapeLadderData]); // Rerun when selections or teams change


    // --- Effect to Calculate Performance Stats (Including Ladder) ---
    useEffect(() => {
        if (allCompletedMentoneGames.length === 0 && !loadingGames) {
            setPerformanceStats({ aggregate: {}, individual: {} });
            return;
        }

        console.log("Recalculating performance stats for selections:", selectedFixtureIds);
        const calculateStats = () => {
            const individualStats = {};
            const aggregate = { wins: 0, draws: 0, losses: 0, gf: 0, ga: 0, gd: 0, gamesPlayed: 0 };

            // Initialize for all teams
            teams.forEach(team => {
                individualStats[team.fixture_id] = {
                    teamName: team.name.replace(/Mentone Hockey Club - |Mentone - /g, ""), // Shorten name
                    wins: 0, draws: 0, losses: 0, gf: 0, ga: 0, gd: 0, gamesPlayed: 0,
                    position: ladderCache[team.fixture_id]?.position ?? null, // Get from cache
                    ladderPoints: ladderCache[team.fixture_id]?.points ?? null, // Get from cache
                    ladderLoading: ladderCache[team.fixture_id]?.isLoading ?? false,
                    ladderError: ladderCache[team.fixture_id]?.error ?? null,
                };
            });

            const relevantGames = allCompletedMentoneGames.filter(game =>
                selectedFixtureIds.includes(game.fixture_id)
            );

            relevantGames.forEach(game => {
                const fixtureId = game.fixture_id;
                if (!selectedFixtureIds.includes(fixtureId)) return; // Should be redundant

                const homeScore = game.home_team?.score;
                const awayScore = game.away_team?.score;
                const isMentoneHome = game.home_team?.club?.toLowerCase() === 'mentone';

                if (typeof homeScore !== 'number' || typeof awayScore !== 'number') return; // Skip invalid

                const goalsFor = isMentoneHome ? homeScore : awayScore;
                const goalsAgainst = isMentoneHome ? awayScore : homeScore;

                const stats = individualStats[fixtureId];
                if (!stats) return; // Safety check

                stats.gamesPlayed += 1;
                stats.gf += goalsFor;
                stats.ga += goalsAgainst;
                stats.gd = stats.gf - stats.ga;

                if (goalsFor > goalsAgainst) stats.wins += 1;
                else if (goalsFor === goalsAgainst) stats.draws += 1;
                else stats.losses += 1;
            });

            // Calculate aggregates from selected individuals
            selectedFixtureIds.forEach(fixtureId => {
                const stats = individualStats[fixtureId];
                if (stats) {
                    aggregate.wins += stats.wins; aggregate.draws += stats.draws; aggregate.losses += stats.losses;
                    aggregate.gf += stats.gf; aggregate.ga += stats.ga; aggregate.gamesPlayed += stats.gamesPlayed;
                }
            });
            aggregate.gd = aggregate.gf - aggregate.ga;

            // Filter final stats to only include selected
            const finalIndividualStats = {};
            selectedFixtureIds.forEach(id => { if (individualStats[id]) finalIndividualStats[id] = individualStats[id]; });

            setPerformanceStats({ aggregate, individual: finalIndividualStats });
            console.log("Stats calculation complete (incl. ladder cache lookup):", { aggregate, individual: finalIndividualStats });
        };

        if (allCompletedMentoneGames.length > 0 || selectedFixtureIds.length === 0) {
            calculateStats();
        }

    }, [selectedFixtureIds, allCompletedMentoneGames, teams, ladderCache, loadingGames]); // Recalculate when selections, games, teams, or cache change

    // Handler for checkbox changes
    const handleTeamSelectionChange = (fixtureId) => {
        setSelectedFixtureIds(prev =>
            prev.includes(fixtureId) ? prev.filter(id => id !== fixtureId) : [...prev, fixtureId]
        );
    };

    // Toggle Select All/None
    const toggleSelectAll = () => {
        if (selectedFixtureIds.length === teams.length) setSelectedFixtureIds([]);
        else setSelectedFixtureIds(teams.map(t => t.fixture_id));
    };

    // Combined loading state
    const isLoading = loadingTeams || loadingGames;

    // --- RENDER SECTION ---
    return (
        <div className="p-4 bg-white rounded-xl shadow-sm">
            {/* Header and Team Selector */}
            <div className="mb-6 flex flex-col sm:flex-row justify-between sm:items-center gap-4">
                <h2 className="text-xl font-bold text-mentone-navy">Club Performance Summary</h2>
                <div className="relative">
                    <button
                        onClick={() => setIsTeamSelectorOpen(!isTeamSelectorOpen)}
                        className={`flex items-center gap-2 text-sm px-4 py-2 rounded-lg border transition-colors w-full sm:w-auto justify-between ${
                            selectedFixtureIds.length > 0
                                ? "bg-mentone-skyblue text-white border-mentone-skyblue"
                                : "bg-white text-mentone-navy border-gray-300 hover:border-mentone-skyblue" // Ensure text is visible
                        }`}
                        disabled={loadingTeams || teams.length === 0}
                    >
                        <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}> <path strokeLinecap="round" strokeLinejoin="round" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" /> </svg>
                        {/* Button Text Logic */}
                        <span className="flex-grow text-left">
                            {loadingTeams ? "Loading Teams..." :
                                teams.length === 0 ? "No Teams Found" :
                                    selectedFixtureIds.length === 0 ? "Select Teams" :
                                        selectedFixtureIds.length === teams.length ? "All Teams Selected" :
                                            `${selectedFixtureIds.length} Team${selectedFixtureIds.length !== 1 ? 's' : ''} Selected`}
                        </span>
                        <svg xmlns="http://www.w3.org/2000/svg" className={`h-4 w-4 transition-transform flex-shrink-0 ${isTeamSelectorOpen ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}> <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" /> </svg>
                    </button>
                    {/* Dropdown Content */}
                    {isTeamSelectorOpen && (
                        <div className="absolute z-20 top-full right-0 mt-1 bg-white border border-gray-200 rounded-lg shadow-lg w-72 max-h-96 overflow-y-auto">
                            <div className="sticky top-0 bg-white px-4 py-2 border-b border-gray-100 flex justify-between items-center">
                                <h3 className="text-sm font-semibold text-mentone-navy">Select Teams</h3>
                                <button onClick={toggleSelectAll} className="text-xs text-mentone-skyblue hover:text-mentone-navy" > {selectedFixtureIds.length === teams.length ? "Deselect All" : "Select All"} </button>
                            </div>
                            <div className="p-2">
                                {teams.map(team => (
                                    <div key={team.fixture_id} className="flex items-center px-2 py-1 hover:bg-gray-100 rounded">
                                        <input type="checkbox" id={`team-select-${team.fixture_id}`} checked={selectedFixtureIds.includes(team.fixture_id)} onChange={() => handleTeamSelectionChange(team.fixture_id)} className="h-4 w-4 text-mentone-skyblue rounded border-gray-300 focus:ring-mentone-skyblue" />
                                        <label htmlFor={`team-select-${team.fixture_id}`} className="ml-2 text-sm text-gray-700 cursor-pointer flex-grow"> {team.name.replace(/Mentone Hockey Club - |Mentone - /g, "")} </label>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            </div>

            {/* Loading State */}
            {isLoading && (
                <div className="flex justify-center items-center h-64"> <ClipLoader color="#0066cc" loading={isLoading} size={50} /> <span className="ml-4 text-mentone-navy">Loading data...</span> </div>
            )}

            {/* Error State */}
            {!isLoading && error && (
                <div className="text-red-600 bg-red-50 p-4 rounded border border-red-200"> <strong>Error:</strong> {error} </div>
            )}

            {/* Data Display Area */}
            {!isLoading && !error && (
                <>
                    {/* Aggregate Summary Cards */}
                    {selectedFixtureIds.length > 0 && (
                        <div className="mb-8 grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 md:gap-4">
                            <StatCard label="Games" value={performanceStats.aggregate.gamesPlayed ?? 0} color="gray" />
                            <StatCard label="Wins" value={performanceStats.aggregate.wins ?? 0} color="green" />
                            <StatCard label="Draws" value={performanceStats.aggregate.draws ?? 0} color="yellow" />
                            <StatCard label="Losses" value={performanceStats.aggregate.losses ?? 0} color="red" />
                            <StatCard label="Goals For" value={performanceStats.aggregate.gf ?? 0} color="blue" />
                            <StatCard label="Goal Diff" value={performanceStats.aggregate.gd ?? 0} color="purple" showSign={true} />
                        </div>
                    )}

                    {/* Individual Team Table */}
                    {selectedFixtureIds.length > 0 && Object.keys(performanceStats.individual).length > 0 ? (
                        <div className="overflow-x-auto">
                            <h3 className="text-lg font-semibold text-mentone-navy mb-3">Individual Team Stats</h3>
                            <table className="min-w-full divide-y divide-gray-200 border border-gray-200">
                                <thead className="bg-gray-50">
                                <tr>
                                    <th scope="col" className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Team</th>
                                    <th scope="col" className="w-12 px-2 py-2 text-center text-xs font-medium text-gray-500 uppercase tracking-wider" title="Position">Pos</th>
                                    <th scope="col" className="w-12 px-2 py-2 text-center text-xs font-medium text-gray-500 uppercase tracking-wider" title="Ladder Points">Pts (L)</th>
                                    <th scope="col" className="w-12 px-2 py-2 text-center text-xs font-medium text-gray-500 uppercase tracking-wider" title="Games Played">GP</th>
                                    <th scope="col" className="w-12 px-2 py-2 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">W</th>
                                    <th scope="col" className="w-12 px-2 py-2 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">D</th>
                                    <th scope="col" className="w-12 px-2 py-2 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">L</th>
                                    <th scope="col" className="w-12 px-2 py-2 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">GF</th>
                                    <th scope="col" className="w-12 px-2 py-2 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">GA</th>
                                    <th scope="col" className="w-12 px-2 py-2 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">GD</th>
                                </tr>
                                </thead>
                                <tbody className="bg-white divide-y divide-gray-200">
                                {Object.entries(performanceStats.individual)
                                    .sort(([, a], [, b]) => a.teamName.localeCompare(b.teamName))
                                    .map(([fixtureId, stats]) => (
                                        <tr key={fixtureId} className="hover:bg-gray-50">
                                            {/* Team Name */}
                                            <td className="px-4 py-2 whitespace-nowrap text-sm font-medium text-gray-900">{stats.teamName}</td>
                                            {/* Ladder Position */}
                                            <td className="px-2 py-2 whitespace-nowrap text-sm text-center text-gray-600">
                                                {stats.ladderLoading ? <ClipLoader size={12} color="#9ca3af"/> : stats.ladderError ? <span title={stats.ladderError} className="text-red-500">!</span> : stats.position ?? '-'}
                                            </td>
                                            {/* Ladder Points */}
                                            <td className="px-2 py-2 whitespace-nowrap text-sm text-center font-semibold text-gray-700">
                                                {stats.ladderLoading ? <ClipLoader size={12} color="#9ca3af"/> : stats.ladderError ? '-' : stats.ladderPoints ?? '-'}
                                            </td>
                                            {/* Game Stats */}
                                            <td className="px-2 py-2 whitespace-nowrap text-sm text-center text-gray-600">{stats.gamesPlayed}</td>
                                            <td className="px-2 py-2 whitespace-nowrap text-sm text-center text-green-600">{stats.wins}</td>
                                            <td className="px-2 py-2 whitespace-nowrap text-sm text-center text-yellow-600">{stats.draws}</td>
                                            <td className="px-2 py-2 whitespace-nowrap text-sm text-center text-red-600">{stats.losses}</td>
                                            <td className="px-2 py-2 whitespace-nowrap text-sm text-center text-blue-600">{stats.gf}</td>
                                            <td className="px-2 py-2 whitespace-nowrap text-sm text-center text-gray-600">{stats.ga}</td>
                                            <td className="px-2 py-2 whitespace-nowrap text-sm text-center font-medium text-purple-600">{stats.gd > 0 ? `+${stats.gd}` : stats.gd}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    ) : !isLoading && selectedFixtureIds.length > 0 ? (
                        <div className="text-center p-6 bg-gray-50 rounded text-gray-600"> No completed game data found for the selected team(s). </div>
                    ) : !isLoading && teams.length > 0 ? (
                        <div className="text-center p-6 bg-blue-50 rounded text-blue-700"> Select one or more teams using the button above to view performance stats. </div>
                    ) : null}
                </>
            )}
            {/* Message if no teams found */}
            {!isLoading && !error && teams.length === 0 && (
                <div className="text-center p-6 bg-yellow-50 rounded text-yellow-700"> No Mentone teams with necessary data (fixture_id, comp_id) were found. </div>
            )}
        </div>
    );
};


// Simple Stat Card Component - Updated to show sign for GD
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
    const displayValue = typeof value === 'number' && showSign && value > 0 ? `+${value}` : value;

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

// Required dependencies:
// npm install axios node-html-parser react-spinners
// or
// yarn add axios node-html-parser react-spinners