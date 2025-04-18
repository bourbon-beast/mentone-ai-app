import { useState, useEffect } from "react";
import { collection, query, getDocs, orderBy, limit } from "firebase/firestore";
import { db } from "../firebase";

const PlayerStats = () => {
    const [players, setPlayers] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [sortField, setSortField] = useState("goals");
    const [filterGender, setFilterGender] = useState("all"); // "all", "Men", "Women"

    useEffect(() => {
        const fetchPlayerStats = async () => {
            try {
                setLoading(true);

                // Get players
                const playersQuery = query(
                    collection(db, "players"),
                    orderBy(sortField, "desc"),
                    limit(50)
                );

                const querySnapshot = await getDocs(playersQuery);
                let playersData = querySnapshot.docs.map(doc => ({
                    id: doc.id,
                    ...doc.data()
                }));

                // Apply gender filter if not "all"
                if (filterGender !== "all") {
                    playersData = playersData.filter(player => player.gender === filterGender);
                }

                setPlayers(playersData);
                setLoading(false);
            } catch (err) {
                console.error("Error fetching player stats:", err);
                setError(err.message);
                setLoading(false);
            }
        };

        fetchPlayerStats();
    }, [sortField, filterGender]);

    const sortBy = (field) => {
        setSortField(field);
    };

    if (loading) {
        return <div className="text-center p-4">Loading player statistics...</div>;
    }

    if (error) {
        return <div className="text-red-600 p-4">Error: {error}</div>;
    }

    return (
        <div className="p-4">
            <div className="flex justify-between items-center mb-6">
                <h2 className="text-2xl font-bold text-blue-600">Player Statistics</h2>

                <div className="flex gap-2">
                    <select
                        value={filterGender}
                        onChange={(e) => setFilterGender(e.target.value)}
                        className="bg-white border border-gray-300 rounded-md px-3 py-1"
                    >
                        <option value="all">All Genders</option>
                        <option value="Men">Men</option>
                        <option value="Women">Women</option>
                    </select>
                </div>
            </div>

            {players.length === 0 ? (
                <div className="text-center p-4 bg-gray-100 rounded-lg">
                    No player data available
                </div>
            ) : (
                <div className="overflow-x-auto">
                    <table className="min-w-full bg-white rounded-lg overflow-hidden">
                        <thead className="bg-gray-200 text-gray-700">
                        <tr>
                            <th className="py-3 px-4 text-left">Name</th>
                            <th className="py-3 px-4 text-left">Team</th>
                            <th className="py-3 px-4 text-center cursor-pointer" onClick={() => sortBy("stats.games_played")}>
                                Games
                                {sortField === "stats.games_played" && " ▼"}
                            </th>
                            <th className="py-3 px-4 text-center cursor-pointer" onClick={() => sortBy("stats.goals")}>
                                Goals
                                {sortField === "stats.goals" && " ▼"}
                            </th>
                            <th className="py-3 px-4 text-center cursor-pointer" onClick={() => sortBy("stats.assists")}>
                                Assists
                                {sortField === "stats.assists" && " ▼"}
                            </th>
                            <th className="py-3 px-4 text-center">Cards</th>
                        </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-200">
                        {players.map((player) => (
                            <tr key={player.id} className="hover:bg-gray-50">
                                <td className="py-2 px-4 font-medium">{player.name}</td>
                                <td className="py-2 px-4">
                                    {player.primary_team_name || "Unknown Team"}
                                </td>
                                <td className="py-2 px-4 text-center">
                                    {player.stats?.games_played || 0}
                                </td>
                                <td className="py-2 px-4 text-center">
                                    {player.stats?.goals || 0}
                                </td>
                                <td className="py-2 px-4 text-center">
                                    {player.stats?.assists || 0}
                                </td>
                                <td className="py-2 px-4 text-center">
                                    {(player.stats?.yellow_cards || 0) + (player.stats?.red_cards || 0)}
                                </td>
                            </tr>
                        ))}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    );
};

export default PlayerStats;