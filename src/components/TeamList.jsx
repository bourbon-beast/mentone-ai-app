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
        return <div className="text-center p-4 text-[var(--color-info)]">Loading teams...</div>;
    }

    if (error) {
        return <div className="text-red-500 p-4">Error: {error}</div>;
    }

    return (
        <div className="p-4 bg-[var(--color-dark)] min-h-screen text-[var(--color-light)]">
            <div className="flex justify-between items-center mb-6">
                <h2 className="text-3xl font-bold text-[var(--color-accent)]">Mentone Teams</h2>
                <div className="flex gap-2">
                    {["all", "Senior", "Junior", "Midweek"].map(type => (
                        <button
                            key={type}
                            onClick={() => setFilter(type)}
                            className={`px-4 py-2 rounded-md font-semibold border 
                            ${
                                filter === type
                                    ? "bg-[var(--color-primary)] text-white border-transparent"
                                    : "bg-[var(--color-light)] text-[var(--color-primary)] border-[var(--color-primary)]"
                            }`}
                        >
                            {type}
                        </button>
                    ))}
                </div>
            </div>

            {teams.length === 0 ? (
                <div className="text-center p-4">No teams found</div>
            ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {teams.map((team) => (
                        <div
                            key={team.id}
                            className="bg-[var(--color-light)] text-[var(--color-primary)] rounded-lg shadow-lg overflow-hidden border border-[var(--color-muted)]"
                        >
                            <div
                                className={`h-2 ${
                                    team.gender === "Men"
                                        ? "bg-[var(--color-men)]"
                                        : team.gender === "Women"
                                            ? "bg-[var(--color-women)]"
                                            : "bg-[var(--color-unknown)]"
                                }`}
                            ></div>
                            <div className="p-4">
                                <h3 className="font-bold text-lg mb-1">{team.name}</h3>
                                <div className="flex justify-between text-sm text-gray-600 mb-3">
                                    <span>{team.type}</span>
                                    <span>{team.gender}</span>
                                </div>
                                <div className="flex justify-end">
                                    <button className="bg-[var(--color-accent)] text-black px-4 py-1 rounded hover:bg-yellow-400 font-medium">
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
