import { useState, useEffect } from "react";
import { collection, query, where, getDocs } from "firebase/firestore";
import { db } from "../firebase";

const TeamList = () => {
    const [teams, setTeams] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [filter, setFilter] = useState("all"); // all, Senior, Junior, or Midweek

    useEffect(() => {
        const fetchTeams = async () => {
            try {
                setLoading(true);
                let teamsQuery;

                if (filter === "all") {
                    teamsQuery = query(
                        collection(db, "teams"),
                        where("is_home_club", "==", true)
                    );
                } else {
                    teamsQuery = query(
                        collection(db, "teams"),
                        where("is_home_club", "==", true),
                        where("type", "==", filter)
                    );
                }

                const querySnapshot = await getDocs(teamsQuery);
                const teamsData = querySnapshot.docs.map(doc => ({
                    id: doc.id,
                    ...doc.data()
                }));

                // Sort by gender, then by type, then by name
                teamsData.sort((a, b) => {
                    if (a.gender !== b.gender) {
                        return a.gender.localeCompare(b.gender);
                    }
                    if (a.type !== b.type) {
                        return a.type.localeCompare(b.type);
                    }
                    return a.name.localeCompare(b.name);
                });

                setTeams(teamsData);
                setLoading(false);
            } catch (err) {
                console.error("Error fetching teams:", err);
                setError(err.message);
                setLoading(false);
            }
        };

        fetchTeams();
    }, [filter]);

    if (loading) {
        return <div className="text-center p-4">Loading teams...</div>;
    }

    if (error) {
        return <div className="text-red-600 p-4">Error: {error}</div>;
    }

    return (
        <div className="p-4">
            <div className="flex justify-between items-center mb-6">
                <h2 className="text-2xl font-bold text-blue-600">Mentone Teams</h2>
                <div className="flex gap-2">
                    <button
                        onClick={() => setFilter("all")}
                        className={`px-4 py-2 rounded-lg ${
                            filter === "all"
                                ? "bg-blue-600 text-white"
                                : "bg-gray-200 text-gray-800"
                        }`}
                    >
                        All
                    </button>
                    <button
                        onClick={() => setFilter("Senior")}
                        className={`px-4 py-2 rounded-lg ${
                            filter === "Senior"
                                ? "bg-blue-600 text-white"
                                : "bg-gray-200 text-gray-800"
                        }`}
                    >
                        Senior
                    </button>
                    <button
                        onClick={() => setFilter("Junior")}
                        className={`px-4 py-2 rounded-lg ${
                            filter === "Junior"
                                ? "bg-blue-600 text-white"
                                : "bg-gray-200 text-gray-800"
                        }`}
                    >
                        Junior
                    </button>
                    <button
                        onClick={() => setFilter("Midweek")}
                        className={`px-4 py-2 rounded-lg ${
                            filter === "Midweek"
                                ? "bg-blue-600 text-white"
                                : "bg-gray-200 text-gray-800"
                        }`}
                    >
                        Midweek
                    </button>
                </div>
            </div>

            {teams.length === 0 ? (
                <div className="text-center p-4">No teams found</div>
            ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {teams.map((team) => (
                        <div
                            key={team.id}
                            className="bg-white rounded-lg shadow-md overflow-hidden border border-gray-200"
                        >
                            <div
                                className={`h-2 ${
                                    team.gender === "Men"
                                        ? "bg-blue-600"
                                        : team.gender === "Women"
                                            ? "bg-pink-500"
                                            : "bg-purple-500"
                                }`}
                            ></div>
                            <div className="p-4">
                                <h3 className="font-bold text-lg mb-2">{team.name}</h3>
                                <div className="flex justify-between text-sm text-gray-600">
                                    <span>{team.type}</span>
                                    <span>{team.gender}</span>
                                </div>
                                <div className="mt-4 flex justify-end">
                                    <button className="bg-blue-600 text-white px-3 py-1 rounded text-sm">
                                        View Schedule
                                    </button>
                                </div>
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
};

export default TeamList;