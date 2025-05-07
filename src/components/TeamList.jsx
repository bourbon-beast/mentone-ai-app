import { useState, useEffect } from "react";
import { collection, query, where, getDocs } from "firebase/firestore";
import { db } from "../firebase";
import { Link } from "react-router-dom";

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
                    if (a.type !== b.type) {
                        return a.type.localeCompare(b.type);
                    }
                    if (a.gender !== b.gender) {
                        return a.gender.localeCompare(b.gender);
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
        return (
            <div className="flex items-center justify-center h-64 bg-white rounded-xl shadow-sm">
                <div className="flex flex-col items-center">
                    <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-mentone-skyblue mb-2"></div>
                    <p className="text-mentone-navy font-medium">Loading teams...</p>
                </div>
            </div>
        );
    }

    if (error) {
        return (
            <div className="bg-red-50 border border-red-200 rounded-xl p-5 text-red-600">
                <p className="font-medium mb-1">Error</p>
                <p className="text-sm">{error}</p>
            </div>
        );
    }

    return (
        <div className="bg-white rounded-xl shadow-sm overflow-hidden">
            {/* Header section */}
            <div className="bg-gradient-to-r from-mentone-navy to-mentone-navy/90 p-5 flex justify-between items-center">
                <h2 className="text-2xl font-bold text-mentone-gold tracking-tight">Mentone Teams</h2>
                <div className="bg-mentone-navy/50 backdrop-blur-sm rounded-lg p-1 flex">
                    {["all", "Senior", "Junior", "Midweek"].map((type) => (
                        <button
                            key={type}
                            onClick={() => setFilter(type)}
                            className={`px-4 py-2 text-sm font-medium rounded-md transition-all ${
                                filter === type
                                    ? "bg-mentone-skyblue text-white shadow-sm"
                                    : "text-white/80 hover:bg-mentone-navy/70 hover:text-white"
                            }`}
                        >
                            {type === "all" ? "All Teams" : type}
                        </button>
                    ))}
                </div>
            </div>

            {/* Team table */}
            <div className="p-5">
                {teams.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-16 bg-gray-50 rounded-lg border border-gray-100">
                        <svg xmlns="http://www.w3.org/2000/svg" className="h-12 w-12 text-gray-300 mb-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
                        </svg>
                        <p className="text-gray-500 font-medium">No teams found</p>
                        <p className="text-gray-400 text-sm mt-1">Try selecting a different category</p>
                    </div>
                ) : (
                    <div className="overflow-x-auto">
                        <table className="min-w-full divide-y divide-gray-200 text-sm">
                            <thead className="bg-gray-50">
                            <tr>
                                <th className="px-4 py-2 text-center font-medium text-gray-500 uppercase">Team</th>
                                <th className="px-4 py-2 text-center font-medium text-gray-500 uppercase">Type</th>
                                <th className="px-4 py-2 text-center font-medium text-gray-500 uppercase">Gender</th>
                                <th className="px-4 py-2 text-center font-medium text-gray-500 uppercase">Competition</th>
                                <th className="px-4 py-2 text-center font-medium text-gray-500 uppercase">Season</th>
                                <th className="px-4 py-2 text-center font-medium text-gray-500 uppercase">Action</th>
                            </tr>
                            </thead>
                            <tbody className="divide-y divide-gray-100">
                            {teams.map((team) => {
                                const teamName = team.name.replace("Mentone Hockey Club - ", "");
                                const competitionName = team.comp_name?.split(" - ")[0] || "Unknown";
                                const season = team.comp_name?.split(" - ")[1] || "2025";

                                return (
                                    <tr key={team.id} className="hover:bg-gray-50 transition-colors">
                                        <td className="px-4 py-2 text-gray-700">{teamName}</td>
                                        <td className="px-4 py-2 text-gray-700">
                                                <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                                                    team.type === "Senior"
                                                        ? "bg-mentone-skyblue/10 text-mentone-skyblue"
                                                        : team.type === "Junior"
                                                            ? "bg-mentone-green/10 text-mentone-green"
                                                            : team.type === "Midweek"
                                                                ? "bg-mentone-gold/10 text-mentone-charcoal"
                                                                : "bg-gray-100 text-gray-600"
                                                }`}>
                                                    {team.type}
                                                </span>
                                        </td>
                                        <td className="px-4 py-2 text-gray-700">{team.gender}</td>
                                        <td className="px-4 py-2 text-gray-700">{competitionName}</td>
                                        <td className="px-4 py-2 text-gray-700">{season}</td>
                                        <td className="px-4 py-2 text-right">
                                            <Link
                                                to={`/teams/${team.id}`}
                                                className="flex items-center justify-center px-3 py-1 bg-mentone-navy text-white rounded-lg hover:bg-mentone-navy/90 transition-colors font-medium text-sm"
                                            >
                                                View Team
                                                <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 ml-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                                                </svg>
                                            </Link>
                                        </td>
                                    </tr>
                                );
                            })}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>
        </div>
    );
};

export default TeamList;