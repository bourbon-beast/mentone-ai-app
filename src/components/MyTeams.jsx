import { useState } from "react";
import { Link } from "react-router-dom";
import { useFavorites } from "../context/FavoritesContext";
import FavoriteButton from "./common/FavoriteButton";

const MyTeams = () => {
    const { favoriteTeams } = useFavorites();
    const [filter, setFilter] = useState("all");

    // Group teams by type
    const teamsByType = favoriteTeams.reduce((acc, team) => {
        const type = team.type || "Other";
        if (!acc[type]) acc[type] = [];
        acc[type].push(team);
        return acc;
    }, {});

    // Filter teams if filter is not "all"
    const filteredTeams = filter === "all"
        ? favoriteTeams
        : favoriteTeams.filter(team => team.type === filter);

    // Count teams by type for the filter buttons
    const teamCounts = Object.entries(teamsByType).reduce((acc, [type, teams]) => {
        acc[type] = teams.length;
        return acc;
    }, {});

    // Get total count for "All" filter
    teamCounts["all"] = favoriteTeams.length;

    return (
        <div className="bg-white rounded-xl shadow-sm overflow-hidden">
            {/* Header */}
            <div className="bg-gradient-to-r from-mentone-navy to-mentone-navy/90 p-5">
                <div className="flex justify-between items-center">
                    <h2 className="text-2xl font-bold text-mentone-gold tracking-tight">My Teams</h2>
                    <div className="flex items-center">
                        <span className="text-mentone-skyblue bg-mentone-navy/60 px-3 py-1 rounded-full text-sm">
                            {favoriteTeams.length} {favoriteTeams.length === 1 ? 'team' : 'teams'} saved
                        </span>
                    </div>
                </div>
                <p className="text-mentone-skyblue/80 text-sm mt-1.5">
                    Manage your favorite teams here. These teams will be highlighted across the application.
                </p>
            </div>

            {/* Team type filter */}
            <div className="bg-mentone-navy/5 border-b border-gray-200 p-4 overflow-x-auto scrollbar-hide">
                <div className="flex space-x-2">
                    <button
                        onClick={() => setFilter("all")}
                        className={`px-3 py-1.5 rounded-full text-sm font-medium flex items-center ${
                            filter === "all"
                                ? "bg-mentone-skyblue text-white"
                                : "bg-white text-gray-700 hover:bg-gray-50"
                        }`}
                    >
                        All Teams
                        <span className="ml-1.5 bg-white/20 text-white px-1.5 py-0.5 rounded-full text-xs">
                            {teamCounts["all"] || 0}
                        </span>
                    </button>

                    {Object.entries(teamsByType).map(([type, teams]) => (
                        <button
                            key={type}
                            onClick={() => setFilter(type)}
                            className={`px-3 py-1.5 rounded-full text-sm font-medium flex items-center ${
                                filter === type
                                    ? type === "Senior"
                                        ? "bg-mentone-skyblue text-white"
                                        : type === "Junior"
                                            ? "bg-mentone-green text-white"
                                            : type === "Midweek"
                                                ? "bg-mentone-gold text-mentone-navy"
                                                : "bg-gray-700 text-white"
                                    : "bg-white text-gray-700 hover:bg-gray-50"
                            }`}
                        >
                            {type}
                            <span className={`ml-1.5 bg-white/20 px-1.5 py-0.5 rounded-full text-xs ${
                                filter === type && type === "Midweek" ? "text-mentone-navy" : "text-white"
                            }`}>
                                {teams.length}
                            </span>
                        </button>
                    ))}
                </div>
            </div>

            {/* Team list */}
            <div className="p-5">
                {favoriteTeams.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-16 bg-gray-50 rounded-lg border border-gray-100">
                        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-12 h-12 text-gray-300 mb-3">
                            <path fillRule="evenodd" d="M10.788 3.21c.448-1.077 1.976-1.077 2.424 0l2.082 5.007 5.404.433c1.164.093 1.636 1.545.749 2.305l-4.117 3.527 1.257 5.273c.271 1.136-.964 2.033-1.96 1.425L12 18.354 7.373 21.18c-.996.608-2.231-.29-1.96-1.425l1.257-5.273-4.117-3.527c-.887-.76-.415-2.212.749-2.305l5.404-.433 2.082-5.006z" clipRule="evenodd" />
                        </svg>
                        <p className="text-gray-500 font-medium">No favorite teams yet</p>
                        <p className="text-gray-400 text-sm mt-1">
                            Add teams to your favorites by clicking the star icon on any team card
                        </p>
                        <Link
                            to="/teams"
                            className="mt-4 px-4 py-2 bg-mentone-skyblue text-white rounded-lg hover:bg-mentone-skyblue/90 transition-colors"
                        >
                            Browse Teams
                        </Link>
                    </div>
                ) : filteredTeams.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-10 bg-gray-50 rounded-lg border border-gray-100">
                        <p className="text-gray-500 font-medium">No teams found with the selected filter</p>
                        <button
                            onClick={() => setFilter("all")}
                            className="mt-3 text-mentone-skyblue hover:text-mentone-navy"
                        >
                            Show all teams
                        </button>
                    </div>
                ) : (
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                        {filteredTeams.map((team) => (
                            <div
                                key={team.id}
                                className="bg-white border border-gray-100 rounded-lg shadow-sm hover:shadow-md transition-all p-4"
                            >
                                <div className="flex justify-between items-start mb-3">
                                    <h3 className="font-bold text-mentone-navy">
                                        {team.name.replace("Mentone Hockey Club - ", "")}
                                    </h3>
                                    <div className="flex gap-2 items-center">
                                        <FavoriteButton team={team} />
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
                                    </div>
                                </div>

                                <div className="space-y-2 mb-3">
                                    <div className="flex justify-between text-sm">
                                        <span className="text-gray-500">Gender</span>
                                        <span className="font-medium text-gray-700">{team.gender}</span>
                                    </div>

                                    <div className="flex justify-between text-sm">
                                        <span className="text-gray-500">Competition</span>
                                        <span className="font-medium text-gray-700">
                                            {team.comp_name?.split(" - ")[0] || "Unknown"}
                                        </span>
                                    </div>

                                    {team.ladder_position && (
                                        <div className="flex justify-between text-sm">
                                            <span className="text-gray-500">Ladder Position</span>
                                            <span className="font-bold text-mentone-navy">
                                                {team.ladder_position}
                                                {team.ladder_points ? ` (${team.ladder_points} pts)` : ''}
                                            </span>
                                        </div>
                                    )}
                                </div>

                                <div className="flex justify-between mt-3 pt-3 border-t border-gray-100">
                                    <Link
                                        to={`/teams/${team.id}`}
                                        className="text-mentone-skyblue hover:text-mentone-navy text-sm flex items-center"
                                    >
                                        View Team Details
                                        <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 ml-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                                        </svg>
                                    </Link>
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
};

export default MyTeams;