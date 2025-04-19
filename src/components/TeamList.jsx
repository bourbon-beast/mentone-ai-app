import { useState, useEffect } from "react";
import { collection, query, where, getDocs } from "firebase/firestore";
import { db } from "../firebase";

const TeamList = () => {
    const [teams, setTeams] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [filter, setFilter] = useState("all");

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
        return <div className="text-red-500 p-4">Error: {error}</div>;
    }

    return (
        <div className="p-6 bg-white">
            <div className="flex flex-col md:flex-row justify-between items-center mb-6">
                <h2 className="text-3xl font-bold text-blue-900 mb-4 md:mb-0">Mentone Teams</h2>
                <div className="flex gap-2 flex-wrap">
                    {["all", "Senior", "Junior", "Midweek"].map(type => (
                        <button
                            key={type}
                            onClick={() => setFilter(type)}
                            className={`px-4 py-2 rounded-md font-semibold 
                            ${
                                filter === type
                                    ? "bg-blue-600 text-white"
                                    : "bg-gray-100 text-gray-800 border border-blue-500 hover:bg-blue-100"
                            }`}
                        >
                            {type === "all" ? "All Teams" : type}
                        </button>
                    ))}
                </div>
            </div>

            {teams.length === 0 ? (
                <div className="text-center p-6 bg-gray-100 rounded-lg border border-gray-300">
                    <p className="text-gray-700 text-lg">No teams found matching the selected filter</p>
                </div>
            ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {teams.map((team) => (
                        <div
                            key={team.id}
                            className="bg-white rounded-lg shadow border border-gray-200 overflow-hidden"
                        >
                            <div
                                className={`h-2 ${
                                    team.gender === "Men"
                                        ? "bg-blue-900"
                                        : team.gender === "Women"
                                            ? "bg-blue-500"
                                            : "bg-green-500"
                                }`}
                            ></div>
                            <div className="p-4">
                                <h3 className="font-bold text-lg mb-2 text-blue-900 truncate" title={team.name}>
                                    {team.name}
                                </h3>
                                <div className="flex justify-between text-sm text-gray-700 mb-4">
                                    <span className="bg-gray-100 px-2 py-1 rounded text-xs font-medium">
                                        {team.type}
                                    </span>
                                    <span className={`px-2 py-1 rounded text-xs font-medium text-white
                                        ${team.gender === "Men"
                                        ? "bg-blue-900"
                                        : team.gender === "Women"
                                            ? "bg-blue-500"
                                            : "bg-green-500"}`}>
                                        {team.gender}
                                    </span>
                                </div>
                                <div className="flex justify-between items-center">
                                    <span className="text-xs text-gray-500">
                                        {team.comp_name ? team.comp_name.split(" - ")[0] : ""}
                                    </span>
                                    <button className="bg-yellow-400 text-blue-900 px-4 py-1 rounded hover:bg-yellow-300 font-medium text-sm flex items-center gap-1">
                                        <span>View Team</span>
                                        <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                                        </svg>
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