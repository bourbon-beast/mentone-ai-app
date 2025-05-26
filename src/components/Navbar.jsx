import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom'; // Import Link and useNavigate
import { useAuth } from '../context/AuthContext'; // Adjust path if necessary

const Navbar = () => {
    const [isOpen, setIsOpen] = useState(false);
    const { currentUser, logout } = useAuth();
    const navigate = useNavigate(); // For programmatic navigation after logout

    const handleLogout = async () => {
        try {
            await logout();
            // Optional: Navigate to homepage or login page after logout
            navigate('/'); 
        } catch (error) {
            console.error("Logout failed:", error);
            // Handle error if needed
        }
    };

    return (
        <nav className="bg-blue-900 shadow-lg">
            <div className="max-w-6xl mx-auto px-4">
                <div className="flex justify-between">
                    <div className="flex space-x-7">
                        <div className="flex items-center py-4">
                            {/* Logo/Club Name */}
                            <span className="font-bold text-white text-lg">Mentone Hockey Club</span>
                        </div>

                        {/* Primary Navigation (Desktop) */}
                        <div className="hidden md:flex items-center space-x-1">
                            <Link to="/" className="py-4 px-2 text-white font-semibold hover:text-blue-300 transition duration-300">Teams</Link>
                            <Link to="/my-teams" className="py-4 px-2 text-gray-300 font-semibold hover:text-white transition duration-300">My Teams</Link>
                            <Link to="/summary" className="py-4 px-2 text-gray-300 font-semibold hover:text-white transition duration-300">Summary</Link> 
                        </div>
                    </div>

                    {/* Secondary Navigation (Desktop - Auth) */}
                    <div className="hidden md:flex items-center space-x-3">
                        {currentUser ? (
                            <>
                                {currentUser.photoURL && (
                                    <img src={currentUser.photoURL} alt="User" className="w-8 h-8 rounded-full" />
                                )}
                                <span className="py-2 px-2 text-gray-300 text-sm">
                                    {currentUser.displayName || currentUser.email}
                                </span>
                                <button 
                                    onClick={handleLogout}
                                    className="py-2 px-3 bg-mentone-skyblue hover:bg-mentone-skyblue/90 text-white text-sm font-semibold rounded-md shadow-sm transition duration-300"
                                >
                                    Logout
                                </button>
                            </>
                        ) : (
                            <Link 
                                to="/login" 
                                className="py-2 px-3 bg-mentone-skyblue hover:bg-mentone-skyblue/90 text-white text-sm font-semibold rounded-md shadow-sm transition duration-300"
                            >
                                Login
                            </Link>
                        )}
                    </div>

                    {/* Mobile menu button */}
                    <div className="md:hidden flex items-center">
                        <button className="outline-none mobile-menu-button" onClick={() => setIsOpen(!isOpen)}>
                            <svg className="w-6 h-6 text-white"
                                 fill="none"
                                 strokeLinecap="round"
                                 strokeLinejoin="round"
                                 strokeWidth="2"
                                 viewBox="0 0 24 24"
                                 stroke="currentColor"
                            >
                                {isOpen ? (
                                    <path d="M6 18L18 6M6 6l12 12" />
                                ) : (
                                    <path d="M4 6h16M4 12h16M4 18h16" />
                                )}
                            </svg>
                        </button>
                    </div>
                </div>
            </div>

            {/* Mobile Menu */}
            <div className={`${isOpen ? 'block' : 'hidden'} md:hidden absolute top-full left-0 right-0 bg-blue-800 z-20`}>
                <div className="flex flex-col items-start py-2">
                    <Link to="/" className="w-full py-3 px-4 text-white font-semibold hover:bg-blue-700 transition duration-300" onClick={() => setIsOpen(false)}>Teams</Link>
                    <Link to="/my-teams" className="w-full py-3 px-4 text-gray-300 font-semibold hover:bg-blue-700 hover:text-white transition duration-300" onClick={() => setIsOpen(false)}>My Teams</Link>
                    <Link to="/summary" className="w-full py-3 px-4 text-gray-300 font-semibold hover:bg-blue-700 hover:text-white transition duration-300" onClick={() => setIsOpen(false)}>Summary</Link>

                    {/* Auth section for mobile */}
                    <div className="w-full px-4 pt-3 pb-2 border-t border-blue-700">
                        {currentUser ? (
                            <>
                                {currentUser.photoURL && (
                                     <img src={currentUser.photoURL} alt="User" className="w-8 h-8 rounded-full mb-2 mx-auto" />
                                )}
                                <p className="text-center text-gray-300 text-sm mb-2">
                                    {currentUser.displayName || currentUser.email}
                                </p>
                                <button 
                                    onClick={() => { handleLogout(); setIsOpen(false); }}
                                    className="w-full py-2 px-3 bg-mentone-skyblue hover:bg-mentone-skyblue/90 text-white text-sm font-semibold rounded-md shadow-sm transition duration-300 mb-2"
                                >
                                    Logout
                                </button>
                            </>
                        ) : (
                            <Link 
                                to="/login" 
                                onClick={() => setIsOpen(false)}
                                className="block w-full text-center py-2 px-3 bg-mentone-skyblue hover:bg-mentone-skyblue/90 text-white text-sm font-semibold rounded-md shadow-sm transition duration-300"
                            >
                                Login
                            </Link>
                        )}
                    </div>
                </div>
            </div>
        </nav>
    );
};

export default Navbar;