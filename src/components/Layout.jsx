// src/components/Layout.jsx
import { NavLink, Outlet } from 'react-router-dom'; // Import NavLink and Outlet

const Layout = () => {
    // Define the active class string for NavLink
    const activeClassName = "border-b-2 border-mentone-skyblue text-mentone-skyblue font-medium";
    const inactiveClassName = "text-gray-600 hover:text-mentone-skyblue";

    return (
        <div className="bg-mentone-offwhite min-h-screen flex flex-col"> {/* Use theme color */}
            {/* Header */}
            <header className="bg-gradient-to-r from-mentone-navy to-mentone-navy/90 text-white shadow-md"> {/* Use theme */}
                <div className="container mx-auto py-4 px-6">
                    <div className="flex justify-between items-center">
                        <h1 className="text-2xl font-bold text-mentone-gold"> {/* Use theme */}
                            Mentone Hockey Club Dashboard
                        </h1>
                        <span className="text-sm opacity-80">Season 2025</span> {/* Adjusted opacity */}
                    </div>
                </div>
            </header>

            {/* Navigation Tabs - Use NavLink */}
            <nav className="bg-white shadow-sm sticky top-0 z-10"> {/* Make nav sticky */}
                <div className="container mx-auto px-6">
                    <div className="flex space-x-1 overflow-x-auto"> {/* Allow horizontal scroll on small screens */}
                        <NavLink
                            to="/" // Link to root for Upcoming Games
                            className={({ isActive }) =>
                                `py-3 px-4 focus:outline-none text-sm whitespace-nowrap ${isActive ? activeClassName : inactiveClassName}`
                            }
                        >
                            Upcoming Games
                        </NavLink>
                        <NavLink
                            to="/teams" // Link to teams list
                            className={({ isActive }) =>
                                `py-3 px-4 focus:outline-none text-sm whitespace-nowrap ${isActive ? activeClassName : inactiveClassName}`
                            }
                        >
                            Teams
                        </NavLink>
                        <NavLink
                            to="/performance" // Link to performance page
                            className={({ isActive }) =>
                                `py-3 px-4 focus:outline-none text-sm whitespace-nowrap ${isActive ? activeClassName : inactiveClassName}`
                            }
                        >
                            Performance
                        </NavLink>
                        <NavLink
                            to="/players" // Link to Player Stats (placeholder)
                            className={({ isActive }) =>
                                `py-3 px-4 focus:outline-none text-sm whitespace-nowrap ${isActive ? activeClassName : inactiveClassName}`
                            }
                        >
                            Player Stats
                        </NavLink>
                        <NavLink
                            to="/summary" // Link to Summary (placeholder)
                            className={({ isActive }) =>
                                `py-3 px-4 focus:outline-none text-sm whitespace-nowrap ${isActive ? activeClassName : inactiveClassName}`
                            }
                        >
                            Weekly Summary
                        </NavLink>
                        <NavLink
                            to="/travel" // Link to Travel Planner
                            className={({ isActive }) =>
                                `py-3 px-4 focus:outline-none text-sm whitespace-nowrap ${isActive ? activeClassName : inactiveClassName}`
                            }
                        >
                            Travel Planner
                        </NavLink>
                        <NavLink
                            to="/venues" // Link to Venue Manager
                            className={({ isActive }) =>
                                `py-3 px-4 focus:outline-none text-sm whitespace-nowrap ${isActive ? activeClassName : inactiveClassName}`
                            }
                        >
                            Venues
                        </NavLink>
                        {/* Add other links as needed */}
                    </div>
                </div>
            </nav>

            {/* Main Content - Outlet renders the matched route's component */}
            <main className="container mx-auto py-6 px-6 flex-grow">
                {/* Removed the extra wrapper div to apply background directly */}
                <Outlet />
            </main>

            {/* Footer */}
            <footer className="bg-mentone-charcoal text-gray-300 py-4"> {/* Use theme */}
                <div className="container mx-auto px-6 text-center text-sm">
                    <p>© {new Date().getFullYear()} Mentone Hockey Club. All data sourced from Hockey Victoria.</p>
                </div>
            </footer>
        </div>
    );
};

export default Layout;