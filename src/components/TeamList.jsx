import { useState, useEffect } from 'react';
import { collection, query, where, getDocs } from 'firebase/firestore';
import { db } from '../firebase';

const TeamList = () => {
    const [teams, setTeams] = useState([]);
    const [loading, setLoading] = useState(true);
    const [filter, setFilter] = useState('all'); // 'all', 'Senior', 'Junior', 'Midweek'
    const [genderFilter, setGenderFilter] = useState('all'); // 'all', 'Men', 'Women'

    useEffect(() => {
        const fetchTeams = async () => {
            try {
                setLoading(true);

                // Base query for Mentone teams
                let q = query(collection(db, "teams"), where("club", "==", "Mentone"));

                const querySnapshot = await getDocs(q);
                const teamsData = [];

                querySnapshot.forEach((doc) => {
                    teamsData.push({ id: doc.id, ...doc.data() });
                });

                // Sort teams by type and then by name
                teamsData.sort((a, b) => {
                    if (a.type !== b.type) {
                        return a.type.localeCompare(b.type);
                    }
                    return a.name.localeCompare(b.name);
                });

                setTeams(teamsData);
                setLoading(false);
            } catch (error) {
                console.error("Error fetching teams:", error);
                setLoading(false);
            }
        };

        fetchTeams();
    }, []);

    // Filter teams based on current filters
    const filteredTeams = teams.filter(team => {
        // Type filter
        if (filter !== 'all' && team.type !== filter) {
            return false;
        }

        // Gender filter
        if (genderFilter !== 'all' && team.gender !== genderFilter) {
            return false;
        }

        return true;
    });

    // Get unique types for filter options
    const types = ['all', ...new Set(teams.map(team => team.type))];
    const genders = ['all', ...new Set(teams.map(team => team.gender))];

    return (
        <div className="bg-white shadow rounded-lg p-6 w-full max-w-6xl mx-auto">
            <div className="flex justify-between items-center mb-6">
                <h2 className="text-2xl font-bold text-blue-900">Mentone Hockey Club Teams</h2>

                <div className="flex space-x-4">
                    {/* Type filter */}
                    <select
                        value={filter}
                        onChange={(e) => setFilter(e.target.value)}
                        className="bg-white border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    >
                        {types.map(type => (
                            <option key={type} value={type}>
                                {type === 'all' ? 'All Types' : type}
                            </option>
                        ))}
                    </select>

                    {/* Gender filter */}
                    <select
                        value={genderFilter}
                        onChange={(e) => setGenderFilter(e.target.value)}
                        className="bg-white border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    >
                        {genders.map(gender => (
                            <option key={gender} value={gender}>
                                {gender === 'all' ? 'All Genders' : gender}
                            </option>
                        ))}
                    </select>
                </div>
            </div>

            {loading ? (
                <div className="flex justify-center items-center h-64">
                    <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-700"></div>
                </div>
            ) : (
                <div className="overflow-x-auto">
                    <table className="min-w-full divide-y divide-gray-200">
                        <thead className="bg-blue-50">
                        <tr>
                            <th className="px-6 py-3 text-left text-xs font-medium text-blue-900 uppercase tracking-wider">
                                Team Name
                            </th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-blue-900 uppercase tracking-wider">
                                Type
                            </th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-blue-900 uppercase tracking-wider">
                                Gender
                            </th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-blue-900 uppercase tracking-wider">
                                Competition
                            </th>
                        </tr>
                        </thead>
                        <tbody className="bg-white divide-y divide-gray-200">
                        {filteredTeams.length > 0 ? (
                            filteredTeams.map((team) => (
                                <tr key={team.id} className="hover:bg-blue-50">
                                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                                        {team.name}
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      <span className={`px-2 py-1 inline-flex text-xs leading-5 font-semibold rounded-full ${
                          team.type === 'Senior' ? 'bg-blue-100 text-blue-800' :
                              team.type === 'Junior' ? 'bg-green-100 text-green-800' :
                                  team.type === 'Midweek' ? 'bg-purple-100 text-purple-800' :
                                      'bg-gray-100 text-gray-800'
                      }`}>
                        {team.type}
                      </span>
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      <span className={`px-2 py-1 inline-flex text-xs leading-5 font-semibold rounded-full ${
                          team.gender === 'Men' ? 'bg-indigo-100 text-indigo-800' :
                              team.gender === 'Women' ? 'bg-pink-100 text-pink-800' :
                                  'bg-gray-100 text-gray-800'
                      }`}>
                        {team.gender}
                      </span>
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                                        {team.comp_name || "Unknown"}
                                    </td>
                                </tr>
                            ))
                        ) : (
                            <tr>
                                <td colSpan="4" className="px-6 py-4 text-center text-sm font-medium text-gray-500">
                                    No teams found matching your filters
                                </td>
                            </tr>
                        )}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    );
};

export default TeamList;