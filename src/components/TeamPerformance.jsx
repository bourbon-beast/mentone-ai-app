// src/components/TeamPerformance.jsx
import React, { useState, useEffect, useCallback, useRef } from 'react';
import { collection, query, where, getDocs, orderBy } from "firebase/firestore";
import { db } from "../firebase";
import { ClipLoader } from 'react-spinners';
import { useFavorites } from "../context/FavoritesContext";
import FilterByFavorites from "./common/FilterByFavorites";

const API_BASE_URL = 'https://ladder-api-55xtnu7seq-uc.a.run.app';

const TeamPerformance = () => {
    const [allCompletedMentoneGames, setAllCompletedMentoneGames] = useState([]);
    const [teams, setTeams] = useState([]);
    const [ladderCache, setLadderCache] = useState({});
    const [selectedFixtureIds, setSelectedFixtureIds] = useState([]);
    const [isTeamSelectorOpen, setIsTeamSelectorOpen] = useState(false);
    const selectorRef = useRef(null);
    const [performanceStats, setPerformanceStats] = useState({ aggregate: {}, individual: {} });
    const [loadingTeams, setLoadingTeams] = useState(true);
    const [loadingGames, setLoadingGames] = useState(false);
    const [error, setError] = useState(null);
    const { showOnlyFavorites, favoriteTeams } = useFavorites();

    useEffect(() => {
        const fetchTeams = async () => {
            setLoadingTeams(true);
            setError(null);
            try {
                const teamsQuery = query(
                    collection(db, "teams"),
                    where("is_home_club", "==", true),
                    orderBy("type"),
                    orderBy("name")
                );
                const snapshot = await getDocs(teamsQuery);
                const teamsData = snapshot.docs.map(doc => {
                    const data = doc.data();
                    if (typeof data.fixture_id !== 'number' || typeof data.comp_id !== 'number') {
                        console.warn(`Team "${data.name}" (ID: ${doc.id}) has invalid or missing fixture_id/comp_id types. Excluding. Fixture: ${data.fixture_id} (${typeof data.fixture_id}), Comp: ${data.comp_id} (${typeof data.comp_id})`);
                        return null;
                    }
                    return {
                        id: doc.id,
                        name: data.name,
                        fixture_id: data.fixture_id,
                        comp_id: data.comp_id,
                        type: data.type,
                    };
                }).filter(Boolean);

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

    useEffect(() => {
        if (teams.length > 0) {
            console.log("[DEBUG] Teams state loaded. Checking fixture_id type of first team:", typeof teams[0].fixture_id, teams[0].fixture_id);
            if (teams.length > 5) {
                console.log("[DEBUG] Checking fixture_id type of 5th team:", typeof teams[5].fixture_id, teams[5].fixture_id);
            }
        }
    }, [teams]);

    useEffect(() => {
        const fetchAllGames = async () => {
            if (teams.length > 0 && allCompletedMentoneGames.length === 0 && !loadingTeams && !loadingGames) {
                setLoadingGames(true);
                setError(null);
                try {
                    const gamesQuery = query(
                        collection(db, "games"),
                        where("mentone_playing", "==", true),
                        where("status", "==", "completed"),
                        orderBy("date", "desc")
                    );
                    const snapshot = await getDocs(gamesQuery);
                    const gamesData = snapshot.docs.map(doc => {
                        const data = doc.data();
                        if (typeof data.fixture_id !== 'number') {
                            console.warn(`Game ${doc.id} has non-numeric fixture_id: ${data.fixture_id} (${typeof data.fixture_id}). Will be ignored by stats calc.`);
                        }
                        return { id: doc.id, ...data };
                    });
                    setAllCompletedMentoneGames(gamesData);
                } catch (err) {
                    console.error("Error fetching completed games:", err);
                    setError("Failed to load game data.");
                    setAllCompletedMentoneGames([]);
                } finally {
                    setLoadingGames(false);
                }
            }
        };
        fetchAllGames();
    }, [teams, loadingTeams, loadingGames]);

    const fetchLadderDataFromAPI = useCallback(async (comp_id, fixture_id) => {
        const numericFixtureId = Number(fixture_id);
        if (isNaN(numericFixtureId)) return;

        if (ladderCache[numericFixtureId]?.isLoading) return;

        setLadderCache(prev => ({
            ...prev,
            [numericFixtureId]: { ...prev[numericFixtureId], isLoading: true, error: null }
        }));

        try {
            const response = await fetch(`${API_BASE_URL}/ladder?comp_id=${comp_id}&fixture_id=${numericFixtureId}`);
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
    }, [ladderCache]);

    useEffect(() => {
        selectedFixtureIds.forEach(fixtureId => {
            const team = teams.find(t => t.fixture_id === fixtureId);
            const needsFetch = team && (
                !ladderCache[fixtureId] ||
                (!ladderCache[fixtureId].isLoading && ladderCache[fixtureId].error !== null) ||
                (!ladderCache[fixtureId].isLoading && ladderCache[fixtureId].position === undefined)
            );

            if (needsFetch) {
                fetchLadderDataFromAPI(Number(team.comp_id), Number(team.fixture_id));
            } else if (!team) {
                if (!ladderCache[fixtureId] || ladderCache[fixtureId]?.error !== "Team info missing") {
                    setLadderCache(prev => ({ ...prev, [fixtureId]: { position: null, points: null, isLoading: false, error: "Team info missing" }}));
                }
            }
        });
    }, [selectedFixtureIds, teams, ladderCache, fetchLadderDataFromAPI]);

    useEffect(() => {
        if (teams.length === 0 || (allCompletedMentoneGames.length === 0 && !loadingGames)) {
            setPerformanceStats({ aggregate: { wins: 0, draws: 0, losses: 0, gf: 0, ga: 0, gd: 0, gamesPlayed: 0 }, individual: {} });
            return;
        }

        const individualStats = {};
        const aggregate = { wins: 0, draws: 0, losses: 0, gf: 0, ga: 0, gd: 0, gamesPlayed: 0 };

        teams.forEach(team => {
            individualStats[team.fixture_id] = {
                teamName: team.name.replace(/Mentone Hockey Club - |Mentone - /g, ""),
                fixture_id: team.fixture_id,
                wins: 0, draws: 0, losses: 0, gf: 0, ga: 0, gd: 0, gamesPlayed: 0,
                position: ladderCache[team.fixture_id]?.position ?? null,
                ladderPoints: ladderCache[team.fixture_id]?.points ?? null,
                ladderLoading: ladderCache[team.fixture_id]?.isLoading ?? false,
                ladderError: ladderCache[team.fixture_id]?.error ?? null,
            };
        });

        const relevantGames = allCompletedMentoneGames.filter(game =>
            typeof game.fixture_id === 'number' && selectedFixtureIds.includes(game.fixture_id)
        );

        relevantGames.forEach(game => {
            const fixtureId = game.fixture_id;
            const stats = individualStats[fixtureId];
            if (!stats) return;

            const homeScore = game.home_team?.score;
            const awayScore = game.away_team?.score;
            if (typeof homeScore !== 'number' || typeof awayScore !== 'number') return;

            const isMentoneHome = game.home_team?.club?.toLowerCase() === 'mentone';
            const goalsFor = isMentoneHome ? homeScore : awayScore;
            const goalsAgainst = isMentoneHome ? awayScore : homeScore;

            stats.gamesPlayed += 1;
            stats.gf += goalsFor;
            stats.ga += goalsAgainst;
            if (goalsFor > goalsAgainst) stats.wins += 1;
            else if (goalsFor === goalsAgainst) stats.draws += 1;
            else stats.losses += 1;
        });

        const finalIndividualStats = {};
        selectedFixtureIds.forEach(fixtureId => {
            const stats = individualStats[fixtureId];
            if (stats) {
                stats.gd = stats.gf - stats.ga;
                finalIndividualStats[fixtureId] = stats;

                aggregate.wins += stats.wins;
                aggregate.draws += stats.draws;
                aggregate.losses += stats.losses;
                aggregate.gf += stats.gf;
                aggregate.ga += stats.ga;
                aggregate.gamesPlayed += stats.gamesPlayed;
            }
        });
        aggregate.gd = aggregate.gf - aggregate.ga;

        setPerformanceStats({ aggregate, individual: finalIndividualStats });
    }, [selectedFixtureIds, allCompletedMentoneGames, teams, ladderCache, loadingGames]);

    const handleTeamSelectionChange = (fixtureId) => {
        const numericFixtureId = Number(fixtureId);
        if (isNaN(numericFixtureId)) return;
        setSelectedFixtureIds(prev =>
            prev.includes(numericFixtureId)
                ? prev.filter(id => id !== numericFixtureId)
                : [...prev, numericFixtureId]
        );
    };

    const toggleSelectAll = () => {
        if (selectedFixtureIds.length === teams.length) {
            setSelectedFixtureIds([]);
        } else {
            const allNumericFixtureIds = teams.map(t => Number(t.fixture_id)).filter(id => !isNaN(id));
            setSelectedFixtureIds(allNumericFixtureIds);
        }
    };

    useEffect(() => {
        const handleClickOutside = (event) => {
            if (selectorRef.current && !selectorRef.current.contains(event.target)) {
                setIsTeamSelectorOpen(false);
            }
        };
        document.addEventListener("mousedown", handleClickOutside);
        return () => document.removeEventListener("mousedown", handleClickOutside);
    }, []);

    const filteredTeams = showOnlyFavorites
        ? teams.filter(team => favoriteTeams.some(fav => fav.id === team.id))
        : teams;

    const filteredTeamsByType = filteredTeams.reduce((acc, team) => {
        const type = team.type || "Other";
        if (!acc[type]) acc[type] = [];
        acc[type].push(team);
        return acc;
    }, {});

    const filteredSortedIndividualStats = Object.values(performanceStats.individual)
        .filter(stats => showOnlyFavorites ? favoriteTeams.some(fav => fav.id === teams.find(t => t.fixture_id === stats.fixture_id)?.id) : true)
        .sort((a, b) => a.teamName.localeCompare(b.teamName));

    const isLoading = loadingTeams || loadingGames;

    return (
        <div className="p-4 bg-white rounded-xl shadow-sm">
            <div className="mb-6 flex flex-col sm:flex-row justify-between sm:items-center gap-4">
                <h2 className="text-xl font-bold text-mentone-navy">Club Performance Summary</h2>
                <div className="flex items-center gap-3">
                    <FilterByFavorites />
                    <div className="relative" ref={selectorRef}>
                        <button
                            onClick={() => setIsTeamSelectorOpen(!isTeamSelectorOpen)}
                            className={`flex items-center gap-2 text-sm px-4 py-2 rounded-lg border transition-colors w-full sm:w-auto justify-between ${
                                selectedFixtureIds.length > 0
                                    ? "bg-mentone-skyblue text-white border-mentone-skyblue"
                                    : "bg-white text-mentone-navy border-gray-300 hover:border-mentone-skyblue"
                            }`}
                            disabled={loadingTeams || filteredTeams.length === 0}
                        >
                            <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                <path strokeLinecap="round" strokeLinejoin="round" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
                            </svg>
                            <span className="flex-grow text-left">
                                {loadingTeams ? "Loading Teams..." :
                                    filteredTeams.length === 0 ? "No Teams Found" :
                                        selectedFixtureIds.length === 0 ? "Select Teams" :
                                            selectedFixtureIds.length === filteredTeams.length ? "All Teams Selected" :
                                                `${selectedFixtureIds.length} Team${selectedFixtureIds.length !== 1 ? 's' : ''} Selected`}
                            </span>
                            <svg xmlns="http://www.w3.org/2000/svg" className={`h-4 w-4 transition-transform flex-shrink-0 ${isTeamSelectorOpen ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                            </svg>
                        </button>
                        {isTeamSelectorOpen && (
                            <div className="absolute z-30 top-full right-0 mt-1 bg-white border border-gray-200 rounded-lg shadow-lg w-72 max-h-96 overflow-y-auto">
                                <div className="sticky top-0 bg-white px-4 py-2 border-b border-gray-100 flex justify-between items-center z-10">
                                    <h3 className="text-sm font-semibold text-mentone-navy">Select Teams</h3>
                                    <button onClick={toggleSelectAll} className="text-xs text-mentone-skyblue hover:text-mentone-navy">
                                        {selectedFixtureIds.length === filteredTeams.length ? "Deselect All" : "Select All"}
                                    </button>
                                </div>
                                <div className="p-2">
                                    {Object.entries(filteredTeamsByType).sort(([typeA], [typeB]) => typeA.localeCompare(typeB))
                                        .map(([type, typeTeams]) => (
                                            <div key={type} className="mb-2">
                                                <h4 className="text-xs font-bold px-2 py-1 bg-gray-100 rounded text-mentone-navy mb-1">{type}</h4>
                                                {typeTeams.sort((a, b) => a.name.localeCompare(b.name))
                                                    .map(team => (
                                                        <div key={team.id} className="flex items-center px-2 py-1 hover:bg-gray-50 rounded">
                                                            <input
                                                                type="checkbox"
                                                                id={`team-select-${team.id}`}
                                                                checked={selectedFixtureIds.includes(Number(team.fixture_id))}
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
            </div>

            {isLoading && (
                <div className="flex justify-center items-center h-64">
                    <ClipLoader color="#4A90E2" loading={isLoading} size={50} />
                    <span className="ml-4 text-mentone-navy">Loading core data...</span>
                </div>
            )}
            {!isLoading && error && (
                <div className="text-red-600 bg-red-50 p-4 rounded border border-red-200">
                    <strong>Error:</strong> {error}
                </div>
            )}
            {!isLoading && !error && (
                <>
                    {selectedFixtureIds.length > 0 ? (
                        <div className="mb-8 grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 md:gap-4">
                            <StatCard label="Games" value={performanceStats.aggregate.gamesPlayed} color="gray" />
                            <StatCard label="Wins" value={performanceStats.aggregate.wins} color="green" />
                            <StatCard label="Draws" value={performanceStats.aggregate.draws} color="yellow" />
                            <StatCard label="Losses" value={performanceStats.aggregate.losses} color="red" />
                            <StatCard label="Goals For" value={performanceStats.aggregate.gf} color="blue" />
                            <StatCard label="Goal Diff" value={performanceStats.aggregate.gd} color="purple" showSign={true} />
                        </div>
                    ) : (
                        !isLoading && filteredTeams.length > 0 && (
                            <div className="mb-8 text-center p-6 text-sm text-gray-500">Select teams to view aggregate stats.</div>
                        )
                    )}
                    {selectedFixtureIds.length > 0 && filteredSortedIndividualStats.length > 0 ? (
                        <div className="overflow-x-auto">
                            <h3 className="text-lg font-semibold text-mentone-navy mb-3">Individual Team Stats</h3>
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
                                {filteredSortedIndividualStats.map((stats) => (
                                    <tr key={stats.fixture_id} className="hover:bg-gray-50">
                                        <td className="px-4 py-2 whitespace-nowrap font-medium text-gray-900">{stats.teamName}</td>
                                        <td className="px-1 py-2 whitespace-nowrap text-center text-gray-600">
                                            {stats.ladderLoading ? <ClipLoader size={12} color="#9ca3af"/> : stats.ladderError ? <span title={stats.ladderError} className="text-red-500 font-bold cursor-help">!</span> : stats.position ?? '-'}
                                        </td>
                                        <td className="px-1 py-2 whitespace-nowrap text-center font-semibold text-gray-700">
                                            {stats.ladderLoading ? <ClipLoader size={12} color="#9ca3af"/> : stats.ladderError ? '-' : stats.ladderPoints ?? '-'}
                                        </td>
                                        <td className="px-1 py-2 whitespace-nowrap text-center text-gray-600">{stats.gamesPlayed}</td>
                                        <td className="px-1 py-2 whitespace-nowrap text-center text-green-600 font-medium">{stats.wins}</td>
                                        <td className="px-1 py-2 whitespace-nowrap text-center text-yellow-600 font-medium">{stats.draws}</td>
                                        <td className="px-1 py-2 whitespace-nowrap text-center text-red-600 font-medium">{stats.losses}</td>
                                        <td className="px-1 py-2 whitespace-nowrap text-center text-blue-600">{stats.gf}</td>
                                        <td className="px-1 py-2 whitespace-nowrap text-center text-gray-600">{stats.ga}</td>
                                        <td className="px-1 py-2 whitespace-nowrap text-center font-medium text-purple-600">
                                            {stats.gd > 0 ? `+${stats.gd}` : stats.gd === 0 && stats.gamesPlayed > 0 ? '0' : stats.gd < 0 ? stats.gd : '-'}
                                        </td>
                                    </tr>
                                ))}
                                </tbody>
                            </table>
                        </div>
                    ) : !isLoading && selectedFixtureIds.length > 0 && filteredSortedIndividualStats.length === 0 ? (
                        <div className="text-center p-6 bg-gray-50 rounded text-gray-600">
                            No completed game data found yet for the selected team(s). Check back later.
                        </div>
                    ) : !isLoading && filteredTeams.length > 0 ? (
                        <div className="text-center p-6 bg-blue-50 rounded text-blue-700 border border-blue-100">
                            Select one or more teams using the button above to view performance stats.
                        </div>
                    ) : null}
                </>
            )}
            {!isLoading && !error && filteredTeams.length === 0 && (
                <div className="text-center p-6 bg-yellow-50 rounded text-yellow-700 border border-yellow-100">
                    {showOnlyFavorites ? "No favorite teams found. Add some favorites or show all teams." : "No active Mentone teams with necessary data (fixture_id, comp_id) were found in the database."}
                </div>
            )}
        </div>
    );
};

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