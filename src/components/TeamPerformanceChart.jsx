import React, { useState, useEffect } from 'react';
import {
    LineChart, Line, XAxis, YAxis, CartesianGrid,
    Tooltip, Legend, ResponsiveContainer
} from 'recharts';
import { collection, query, where, getDocs, orderBy } from "firebase/firestore";
import { db } from "../firebase";

const TeamPerformanceChart = () => {
    const [performanceData, setPerformanceData] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [selectedTeam, setSelectedTeam] = useState(null);
    const [teams, setTeams] = useState([]);

    useEffect(() => {
        // Fetch available teams
        const fetchTeams = async () => {
            try {
                const teamsQuery = query(
                    collection(db, "teams"),
                    where("is_home_club", "==", true)
                );

                const snapshot = await getDocs(teamsQuery);
                const teamsData = snapshot.docs.map(doc => ({
                    id: doc.id,
                    name: doc.data().name
                }));

                setTeams(teamsData);

                // Select first team by default
                if (teamsData.length > 0 && !selectedTeam) {
                    setSelectedTeam(teamsData[0].id);
                }
            } catch (err) {
                console.error("Error fetching teams:", err);
                setError("Failed to load teams");
            }
        };

        fetchTeams();
    }, []);

    useEffect(() => {
        // Only fetch performance data if a team is selected
        if (selectedTeam) {
            fetchTeamPerformance(selectedTeam);
        }
    }, [selectedTeam]);

    const fetchTeamPerformance = async (teamId) => {
        try {
            setLoading(true);

            // Get all games for the selected team
            const gamesQuery = query(
                collection(db, "games"),
                where("status", "==", "completed"),
                orderBy("date", "asc")
            );

            const querySnapshot = await getDocs(gamesQuery);
            const games = querySnapshot.docs.map(doc => ({
                id: doc.id,
                ...doc.data()
            }));

            // Filter games for the selected team and build performance data
            const teamGames = games.filter(game =>
                (game.home_team?.id === teamId || game.away_team?.id === teamId) &&
                game.home_team?.score !== undefined &&
                game.away_team?.score !== undefined
            );

            // Create performance data points
            let cumulativeGoalsFor = 0;
            let cumulativeGoalsAgainst = 0;
            let points = 0;

            const performanceData = teamGames.map((game, index) => {
                const gameDate = game.date?.toDate ? game.date.toDate() : new Date(game.date);
                const isMentoneHome = game.home_team?.id === teamId;

                const goalsFor = isMentoneHome ? game.home_team.score : game.away_team.score;
                const goalsAgainst = isMentoneHome ? game.away_team.score : game.home_team.score;

                // Update cumulative stats
                cumulativeGoalsFor += goalsFor;
                cumulativeGoalsAgainst += goalsAgainst;

                // Calculate points (3 for win, 1 for draw, 0 for loss)
                if (goalsFor > goalsAgainst) {
                    points += 3;
                } else if (goalsFor === goalsAgainst) {
                    points += 1;
                }

                // Calculate game number (round)
                const gameNumber = index + 1;

                return {
                    gameNumber,
                    date: gameDate.toLocaleDateString("en-AU", { month: 'short', day: 'numeric' }),
                    goalsFor,
                    goalsAgainst,
                    cumulativeGoalsFor,
                    cumulativeGoalsAgainst,
                    goalDifference: goalsFor - goalsAgainst,
                    cumulativeGoalDifference: cumulativeGoalsFor - cumulativeGoalsAgainst,
                    points,
                };
            });

            setPerformanceData(performanceData);
            setLoading(false);
        } catch (err) {
            console.error("Error fetching team performance:", err);
            setError(err.message);
            setLoading(false);
        }
    };

    const handleTeamChange = (e) => {
        setSelectedTeam(e.target.value);
    };

    if (loading && !performanceData.length) {
        return <div className="flex justify-center items-center h-64">Loading performance data...</div>;
    }

    if (error) {
        return <div className="text-red-500 p-4">Error: {error}</div>;
    }

    const selectedTeamName = teams.find(team => team.id === selectedTeam)?.name || "Selected Team";

    return (
        <div className="p-4 bg-white rounded-lg">
            <div className="mb-6 flex justify-between items-center">
                <h2 className="text-xl font-bold text-gray-800">Team Performance</h2>
                <select
                    value={selectedTeam || ''}
                    onChange={handleTeamChange}
                    className="border border-gray-300 rounded px-3 py-2 bg-white"
                >
                    <option value="" disabled>Select a team</option>
                    {teams.map(team => (
                        <option key={team.id} value={team.id}>{team.name}</option>
                    ))}
                </select>
            </div>

            {performanceData.length === 0 ? (
                <div className="text-center p-6 bg-gray-50 rounded">
                    No game data available for {selectedTeamName}
                </div>
            ) : (
                <div className="h-80">
                    <ResponsiveContainer width="100%" height="100%">
                        <LineChart
                            data={performanceData}
                            margin={{ top: 5, right: 30, left: 20, bottom: 5 }}
                        >
                            <CartesianGrid strokeDasharray="3 3" />
                            <XAxis dataKey="gameNumber" label={{ value: 'Game Number', position: 'insideBottomRight', offset: -10 }} />
                            <YAxis />
                            <Tooltip formatter={(value, name) => [value, name.replace(/([A-Z])/g, ' $1').trim()]} />
                            <Legend />
                            <Line type="monotone" dataKey="points" stroke="#0066cc" name="Points" strokeWidth={2} />
                            <Line type="monotone" dataKey="cumulativeGoalDifference" stroke="#ff9500" name="Goal Difference" dot={{ r: 3 }} />
                        </LineChart>
                    </ResponsiveContainer>
                </div>
            )}

            {performanceData.length > 0 && (
                <div className="mt-6 grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div className="bg-blue-100 p-4 rounded-lg text-center">
                        <div className="text-lg font-bold text-blue-800">
                            {performanceData[performanceData.length - 1].points}
                        </div>
                        <div className="text-sm text-blue-600">Total Points</div>
                    </div>
                    <div className="bg-green-100 p-4 rounded-lg text-center">
                        <div className="text-lg font-bold text-green-800">
                            {performanceData[performanceData.length - 1].cumulativeGoalsFor}
                        </div>
                        <div className="text-sm text-green-600">Goals For</div>
                    </div>
                    <div className="bg-red-100 p-4 rounded-lg text-center">
                        <div className="text-lg font-bold text-red-800">
                            {performanceData[performanceData.length - 1].cumulativeGoalsAgainst}
                        </div>
                        <div className="text-sm text-red-600">Goals Against</div>
                    </div>
                    <div className="bg-purple-100 p-4 rounded-lg text-center">
                        <div className="text-lg font-bold text-purple-800">
                            {performanceData[performanceData.length - 1].cumulativeGoalDifference}
                        </div>
                        <div className="text-sm text-purple-600">Goal Difference</div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default TeamPerformanceChart;