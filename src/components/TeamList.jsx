import { useState, useEffect, useCallback } from "react";
import { collection, query, where, getDocs } from "firebase/firestore";
import { db } from "../firebase";
import { Link } from "react-router-dom";
import { useFavorites } from "../context/FavoritesContext";
import FavoriteButton from "./common/FavoriteButton";
import FilterByFavorites from "./common/FilterByFavorites";

const API_BASE_URL = 'https://ladder-api-55xtnu7seq-uc.a.run.app';

const TeamList = () => {
    const [teams, setTeams] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [filter, setFilter] = useState("all");
    const [search, setSearch] = useState("");
    const [ladderPositions, setLadderPositions] = useState({});
    const { showOnlyFavorites, favoriteTeams } = useFavorites();

    const fetchLadderData = useCallback(async (comp_id, fixture_id, teamId) => {
        try {
            const response = await fetch(`${API_BASE_URL}/ladder?comp_id=${comp_id}&fixture_id=${fixture_id}`);
            if (!response.ok) {
                throw new Error(`Ladder API Error (${response.status})`);
            }
            const data = await response.json();
            setLadderPositions(prev => ({
                ...prev,
                [teamId]: data.position ?? '-'
            }));
        } catch (error) {
            console.error(`Error fetching ladder for team ${teamId}:`, error);
            setLadderPositions(prev => ({
                ...prev,
                [teamId]: '-'
            }));
        }
    }, []);

    useEffect(() => {
        const fetchTeams = async () => {
            try {
                setLoading(true);
                let teamsQuery = query(
                    collection(db, "teams"),
                    where("is_home_club", "==", true)
                );

                if (filter !== "all") {
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

                teamsData.sort((a, b) => a.comp_name.localeCompare(b.comp_name));
                setTeams(teamsData);

                teamsData.forEach(team => {
                    if (team.comp_id && team.fixture_id) {
                        fetchLadderData(team.comp_id, team.fixture_id, team.id);
                    } else {
                        setLadderPositions(prev => ({
                            ...prev,
                            [team.id]: '-'
                        }));
                    }
                });

                setLoading(false);
            } catch (err) {
                console.error("Error fetching teams:", err);
                setError(err.message);
                setLoading(false);
            }
        };

        fetchTeams();
    }, [filter, fetchLadderData]);

    const filteredTeams = teams
        .filter(team =>
            showOnlyFavorites
                ? favoriteTeams.some(fav => fav.id === team.id)
                : true
        )
        .filter(team =>
            team.comp_name.toLowerCase().includes(search.toLowerCase()) ||
            team.gender.toLowerCase().includes(search.toLowerCase())
        );

    if (loading) {
        return (
            <div className="flex items-center justify-center h-64 bg-white rounded-xl shadow-sm">
                <div className="flex flex-col items-center">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-mentone-skyblue mb-2"></div>
                    <p className="text-mentone-navy text-sm">Loading teams...</p>
                </div>
            </div>
        );
    }

    if (error) {
        return (
            <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-red-600">
                <p className="font-medium text-sm">Error: {error}</p>
            </div>
        );
    }

    return (
        <div className="bg-white rounded-xl shadow-sm">
            <div className="p-4 border-b border-gray-100">
                <div className="flex flex-col sm:flex-row justify-between items-center gap-3">
                    <h2 className="text-xl font-bold text-mentone-navy">Mentone Teams</h2>
                    <div className="flex items-center gap-3 w-full sm:w-auto">
                        <input
                            type="text"
                            placeholder="Search teams..."
                            value={search}
                            onChange={(e) => setSearch(e.target.value)}
                            className="w-full sm:w-64 px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-mentone-skyblue"
                        />
                        <FilterByFavorites />
                    </div>
                </div>
                <div className="flex gap-2 mt-3 overflow-x-auto pb-2">
                    {["all", "Senior", "Junior", "Midweek", "Masters"].map((type) => (
                        <button
                            key={type}
                            onClick={() => setFilter(type)}
                            className={`px-3 py-1 text-sm font-medium rounded-full whitespace-nowrap ${
                                filter === type
                                    ? "bg-mentone-skyblue text-white"
                                    : "bg-gray-100 text-gray-600 hover:bg-gray-200"
                            }`}
                        >
                            {type === "all" ? "All" : type}
                        </button>
                    ))}
                </div>
            </div>
            {filteredTeams.length === 0 ? (
                <div className="p-6 text-center">
                    <svg xmlns="http://www.w3.org/2000/svg" className="h-10 w-10 text-gray-300 mx-auto mb-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
                    </svg>
                    <p className="text-gray-500 text-sm">No teams found</p>
                    <p className="text-gray-400 text-xs mt-1">
                        {showOnlyFavorites ? "No favorite teams. Add some or view all." : "Try a different filter or search term."}
                    </p>
                </div>
            ) : (
                <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                        <thead>
                        <tr className="border-b border-gray-100">
                            <th className="p-3 text-left font-medium text-gray-600">Competition</th>
                            <th className="p-3 text-left font-medium text-gray-600">Type</th>
                            <th className="p-3 text-left font-medium text-gray-600">Gender</th>
                            <th className="p-3 text-left font-medium text-gray-600">Season</th>
                            <th className="p-3 text-left font-medium text-gray-600">Ladder Position</th>
                            <th className="p-3 text-left font-medium text-gray-600"></th>
                        </tr>
                        </thead>
                        <tbody>
                        {filteredTeams.map((team) => (
                            <tr key={team.id} className="border-b border-gray-100 hover:bg-gray-50">
                                <td className="p-3">
                                    <Link to={`/teams/${team.id}`} className="text-mentone-navy font-medium text-left hover:underline">
                                        {team.comp_name.split(" - ")[0]}
                                    </Link>
                                </td>
                                <td className="p-3">
                                        <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                                            team.type === "Senior" ? "bg-mentone-skyblue/10 text-mentone-skyblue" :
                                                team.type === "Junior" ? "bg-mentone-green/10 text-mentone-green" :
                                                    team.type === "Midweek" ? "bg-mentone-gold/10 text-mentone-charcoal" :
                                                        "bg-gray-100 text-gray-600"
                                        }`}>
                                            {team.type}
                                        </span>
                                </td>
                                <td className="p-3 text-gray-700">{team.gender}</td>
                                <td className="p-3 text-gray-700">{team.comp_name.split(" - ")[1] || "2025"}</td>
                                <td className="p-3 text-gray-700">{ladderPositions[team.id] || '-'}</td>
                                <td className="p-3">
                                    <FavoriteButton team={team} />
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

export default TeamList;