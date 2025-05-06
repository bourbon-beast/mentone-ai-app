import { useState, useEffect } from "react";
import { collection, query, orderBy, getDocs } from "firebase/firestore";
import { db } from "../firebase";

const VenueManager = () => {
    const [venues, setVenues] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [searchTerm, setSearchTerm] = useState("");
    const [filter, setFilter] = useState("all");

    useEffect(() => {
        const fetchVenues = async () => {
            try {
                setLoading(true);

                // Query all venues
                const venuesQuery = query(
                    collection(db, "venues"),
                    orderBy("name", "asc")
                );

                const querySnapshot = await getDocs(venuesQuery);
                const venuesData = querySnapshot.docs.map(doc => ({
                    id: doc.id,
                    ...doc.data()
                }));

                setVenues(venuesData);
                setLoading(false);
            } catch (err) {
                console.error("Error fetching venues:", err);
                setError(err.message);
                setLoading(false);
            }
        };

        fetchVenues();
    }, []);

    // Filter venues based on search term and filter
    const filteredVenues = venues.filter(venue => {
        const matchesSearch =
            searchTerm === "" ||
            venue.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
            (venue.address && venue.address.toLowerCase().includes(searchTerm.toLowerCase()));

        // Apply filter if not "all"
        if (filter === "all") return matchesSearch;
        if (filter === "with-address") return matchesSearch && venue.address;
        if (filter === "no-address") return matchesSearch && !venue.address;

        return matchesSearch;
    });

    if (loading) {
        return (
            <div className="flex items-center justify-center h-64 bg-white rounded-xl shadow-sm">
                <div className="flex flex-col items-center">
                    <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-mentone-skyblue mb-2"></div>
                    <p className="text-mentone-navy font-medium">Loading venues...</p>
                </div>
            </div>
        );
    }

    if (error) {
        return (
            <div className="bg-red-50 border border-red-200 rounded-xl p-5 text-red-600">
                <p className="font-medium mb-1">Error Loading Venues</p>
                <p className="text-sm">{error}</p>
            </div>
        );
    }

    return (
        <div className="bg-white rounded-xl shadow-sm overflow-hidden">
            {/* Header */}
            <div className="bg-gradient-to-r from-mentone-navy to-mentone-navy/90 p-5">
                <h2 className="text-2xl font-bold text-mentone-gold tracking-tight">Venue Database</h2>
                <p className="text-mentone-skyblue text-sm mt-1">
                    {venues.length} venues available for travel planning
                </p>
            </div>

            {/* Search and Filter Controls */}
            <div className="bg-mentone-navy/5 p-4 border-b border-gray-200">
                <div className="flex flex-col sm:flex-row justify-between gap-4">
                    {/* Search Input */}
                    <div className="relative flex-grow max-w-md">
                        <input
                            type="text"
                            placeholder="Search venues..."
                            value={searchTerm}
                            onChange={(e) => setSearchTerm(e.target.value)}
                            className="w-full px-4 py-2 pr-10 rounded-lg border border-gray-300 focus:ring-2 focus:ring-mentone-skyblue focus:border-transparent"
                        />
                        <div className="absolute right-3 top-2.5 text-gray-400">
                            <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                            </svg>
                        </div>
                    </div>

                    {/* Filter Buttons */}
                    <div className="flex bg-white rounded-lg shadow-sm border border-gray-200">
                        <button
                            onClick={() => setFilter("all")}
                            className={`px-4 py-2 text-sm font-medium rounded-l-lg ${
                                filter === "all"
                                    ? "bg-mentone-skyblue text-white"
                                    : "bg-white text-gray-700 hover:bg-gray-50"
                            }`}
                        >
                            All Venues
                        </button>
                        <button
                            onClick={() => setFilter("with-address")}
                            className={`px-4 py-2 text-sm font-medium ${
                                filter === "with-address"
                                    ? "bg-mentone-skyblue text-white"
                                    : "bg-white text-gray-700 hover:bg-gray-50"
                            }`}
                        >
                            With Address
                        </button>
                        <button
                            onClick={() => setFilter("no-address")}
                            className={`px-4 py-2 text-sm font-medium rounded-r-lg ${
                                filter === "no-address"
                                    ? "bg-mentone-skyblue text-white"
                                    : "bg-white text-gray-700 hover:bg-gray-50"
                            }`}
                        >
                            Missing Address
                        </button>
                    </div>
                </div>
            </div>

            {/* Venue List */}
            <div className="p-5">
                {filteredVenues.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-16 bg-gray-50 rounded-lg border border-gray-100">
                        <svg xmlns="http://www.w3.org/2000/svg" className="h-12 w-12 text-gray-300 mb-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
                        </svg>
                        <p className="text-gray-500 font-medium">No venues found</p>
                        <p className="text-gray-400 text-sm mt-1">Try adjusting your search or filter</p>
                    </div>
                ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
                        {filteredVenues.map(venue => (
                            <div
                                key={venue.id}
                                className="bg-white border border-gray-200 rounded-lg shadow-sm hover:shadow-md transition-all duration-300"
                            >
                                <div className="p-4">
                                    <h3 className="font-bold text-lg text-mentone-navy">{venue.name}</h3>

                                    {venue.address ? (
                                        <p className="text-gray-600 text-sm mt-2">{venue.address}</p>
                                    ) : (
                                        <p className="text-yellow-600 text-sm mt-2 italic">Address information missing</p>
                                    )}

                                    {venue.field_code && (
                                        <div className="flex items-center mt-2">
                                            <span className="text-xs px-2 py-1 bg-mentone-offwhite text-mentone-navy rounded font-medium">
                                                Field: {venue.field_code}
                                            </span>
                                        </div>
                                    )}

                                    <div className="mt-4 pt-3 border-t border-gray-100 flex justify-end">
                                        <a
                                            href={`https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(venue.address || venue.name + ', Victoria, Australia')}`}
                                            target="_blank"
                                            rel="noopener noreferrer"
                                            className="text-mentone-skyblue hover:text-mentone-navy text-sm flex items-center"
                                        >
                                            <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
                                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
                                            </svg>
                                            View on Google Maps
                                        </a>
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </div>

            {/* Stats footer */}
            <div className="bg-gray-50 p-4 border-t border-gray-200 text-sm text-gray-600">
                <div className="flex flex-wrap gap-4 justify-between">
                    <div>
                        Showing {filteredVenues.length} of {venues.length} venues
                    </div>
                    <div>
                        {venues.filter(v => v.address).length} venues with addresses / {venues.filter(v => !v.address).length} missing addresses
                    </div>
                </div>
            </div>
        </div>
    );
};
    export default VenueManager;