import { useState } from 'react';

const Navbar = () => {
    const [isOpen, setIsOpen] = useState(false);

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
                            <a href="/" className="py-4 px-2 text-white font-semibold border-b-2 border-blue-500">Teams</a>
                            <a href="/games" className="py-4 px-2 text-gray-300 font-semibold hover:text-white hover:border-b-2 hover:border-blue-500 transition duration-300">Games</a>
                            <a href="/players" className="py-4 px-2 text-gray-300 font-semibold hover:text-white hover:border-b-2 hover:border-blue-500 transition duration-300">Players</a>
                            <a href="/stats" className="py-4 px-2 text-gray-300 font-semibold hover:text-white hover:border-b-2 hover:border-blue-500 transition duration-300">Stats</a>
                        </div>
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
            <div className={`${isOpen ? 'block' : 'hidden'} md:hidden`}>
                <div className="flex flex-col items-start py-2 bg-blue-800">
                    <a href="/" className="w-full py-2 px-4 text-white font-semibold bg-blue-700">Teams</a>
                    <a href="/games" className="w-full py-2 px-4 text-gray-300 font-semibold hover:bg-blue-700 hover:text-white transition duration-300">Games</a>
                    <a href="/players" className="w-full py-2 px-4 text-gray-300 font-semibold hover:bg-blue-700 hover:text-white transition duration-300">Players</a>
                    <a href="/stats" className="w-full py-2 px-4 text-gray-300 font-semibold hover:bg-blue-700 hover:text-white transition duration-300">Stats</a>
                </div>
            </div>
        </nav>
    );
};

export default Navbar;