"use client";

import React, { useState, useEffect, createContext, useContext, useCallback, useRef, FormEvent } from 'react';

// --- TYPE DEFINITIONS ---
interface User {
    id: number;
    username: string;
    email: string;
    thread_id: string;
    age?: number;
    risk_tolerance?: string;
}

interface AuthContextType {
    token: string | null;
    setToken: (token: string | null) => void;
    logout: () => void;
    user: User | null;
    fetchUserProfile: () => Promise<void>;
    isLoading: boolean;
}

interface Message {
    id: number;
    content: string;
    isUser: boolean;
    isLoading?: boolean;
    toolStatus?: string | null;
}

interface InputBarProps {
    currentMessage: string;
    setCurrentMessage: (value: string) => void;
    onSubmit: (e: FormEvent) => void;
    isStreaming: boolean;
    onFileUpload: (file: File) => void;
}

interface StreamedEvent {
    type: 'content' | 'tool_start' | 'tool_end' | 'error' | 'end';
    content?: string;
}

// --- CONSTANTS ---
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

// --- Authentication Context ---
const AuthContext = createContext<AuthContextType | null>(null);

export const AuthProvider = ({ children }: { children: React.ReactNode }) => {
    const [token, setToken] = useState<string | null>(null);
    const [user, setUser] = useState<User | null>(null);
    const [isLoading, setIsLoading] = useState(true);

    const logout = useCallback(() => {
        setToken(null);
        setUser(null);
        localStorage.removeItem('nivara_token');
    }, []);

    const internalFetchUserProfile = useCallback(async (currentToken: string) => {
        try {
            const response = await fetch(`${API_URL}/users/me`, {
                headers: { 'Authorization': `Bearer ${currentToken}` }
            });
            if (!response.ok) throw new Error("Failed to fetch user profile.");
            const userData: User = await response.json();
            setUser(userData);
        } catch (error) {
            console.error(error);
            logout();
        }
    }, [logout]);

    useEffect(() => {
        const storedToken = localStorage.getItem('nivara_token');
        if (storedToken) {
            setToken(storedToken);
            internalFetchUserProfile(storedToken).finally(() => setIsLoading(false));
        } else {
            setIsLoading(false);
        }
    }, [internalFetchUserProfile]);

    const handleSetToken = (newToken: string | null) => {
        setIsLoading(true);
        if (newToken) {
            setToken(newToken);
            localStorage.setItem('nivara_token', newToken);
            internalFetchUserProfile(newToken).finally(() => setIsLoading(false));
        } else {
            logout();
            setIsLoading(false);
        }
    };

    const refreshProfile = async () => {
        if (token) {
            await internalFetchUserProfile(token);
        }
    };

    return (
        <AuthContext.Provider value={{ token, setToken: handleSetToken, logout, user, fetchUserProfile: refreshProfile, isLoading }}>
            {children}
        </AuthContext.Provider>
    );
};

export const useAuth = () => {
    const context = useContext(AuthContext);
    if (!context) throw new Error('useAuth must be used within an AuthProvider');
    return context;
};

// --- UI Components ---
const Header = ({ onNewChat }: { onNewChat: () => void }) => {
    const { user, logout } = useAuth();
    const [isMenuOpen, setIsMenuOpen] = useState(false);
    const menuRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        const handleClickOutside = (event: MouseEvent) => {
            if (menuRef.current && !menuRef.current.contains(event.target as Node)) setIsMenuOpen(false);
        };
        document.addEventListener("mousedown", handleClickOutside);
        return () => document.removeEventListener("mousedown", handleClickOutside);
    }, []);

    if (!user) return null;

    return (
        <header className="absolute top-0 left-0 right-0 flex items-center justify-between p-4 z-10 w-full">
            <div className="flex items-center space-x-4">
                <span className="font-semibold text-lg text-gray-300">Nivara</span>
                <button
                    onClick={onNewChat}
                    className="p-2 rounded-full hover:bg-gray-700 transition-colors"
                    title="New Chat"
                >
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-5 h-5 text-gray-300">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
                    </svg>
                </button>
            </div>
            <div className="relative" ref={menuRef}>
                <button
                    onClick={() => setIsMenuOpen(!isMenuOpen)}
                    className="w-8 h-8 rounded-full bg-gradient-to-br from-purple-500 to-blue-500 flex items-center justify-center text-white font-bold focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-gray-900 focus:ring-white"
                >
                    {user.username.charAt(0).toUpperCase()}
                </button>
                {isMenuOpen && (
                    <div className="absolute right-0 mt-2 w-56 bg-gray-800 rounded-md shadow-lg py-1 text-white">
                        <div className="px-4 py-2 text-sm text-gray-400 border-b border-gray-700">
                            Signed in as <br />
                            <span className="font-medium text-gray-200 truncate">{user.email}</span>
                        </div>
                        <button
                            onClick={() => { logout(); setIsMenuOpen(false); }}
                            className="block w-full text-left px-4 py-2 text-sm hover:bg-gray-700"
                        >
                            Logout
                        </button>
                    </div>
                )}
            </div>
        </header>
    );
};

const InputBar = ({ currentMessage, setCurrentMessage, onSubmit, isStreaming, onFileUpload }: InputBarProps) => {
    const fileInputRef = useRef<HTMLInputElement>(null);

    const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        if (e.target.files && e.target.files.length > 0) {
            onFileUpload(e.target.files[0]);
            // Reset input so the same file can be uploaded again if needed
            if (fileInputRef.current) fileInputRef.current.value = '';
        }
    };

    return (
        <form onSubmit={onSubmit} className="w-full max-w-4xl p-4">
            <div className="relative flex items-center gap-2">
                <input
                    type="file"
                    accept=".csv"
                    className="hidden"
                    ref={fileInputRef}
                    onChange={handleFileChange}
                />
                <button
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    disabled={isStreaming}
                    className="p-3 rounded-full bg-[#1E1F20] border border-gray-600/50 hover:bg-gray-700 disabled:opacity-50 transition-colors flex-shrink-0"
                    title="Upload Bank Statement (CSV)"
                >
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-6 h-6 text-gray-300">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 0 0-3.375-3.375h-1.5A1.125 1.125 0 0 1 13.5 7.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H8.25m6.75 12-3-3m0 0-3 3m3-3v6m-1.5-15H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 0 0-9-9Z" />
                    </svg>
                </button>
                <div className="relative w-full">
                    <input
                        type="text"
                        value={currentMessage}
                        onChange={(e) => setCurrentMessage(e.target.value)}
                        disabled={isStreaming}
                        placeholder="Ask Nivara or Upload a CSV for Tax Advice..."
                        className="w-full bg-[#1E1F20] border border-gray-600/50 rounded-full h-16 pl-6 pr-16 text-gray-200 text-lg focus:outline-none focus:ring-2 focus:ring-blue-500/50 transition-all"
                    />
                    <div className="absolute inset-y-0 right-0 flex items-center pr-2">
                        <button type="submit" disabled={isStreaming || !currentMessage.trim()} className="p-2 mr-2 rounded-full bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700 disabled:opacity-50 transition-colors">
                            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-6 h-6 text-white">
                                <path d="M3.478 2.404a.75.75 0 0 0-.926.941l2.432 7.905H13.5a.75.75 0 0 1 0 1.5H4.984l-2.432 7.905a.75.75 0 0 0 .926.94 60.519 60.519 0 0 0 18.445-8.986.75.75 0 0 0 0-1.218A60.517 60.517 0 0 0 3.478 2.404Z" />
                            </svg>
                        </button>
                    </div>
                </div>
            </div>
        </form>
    );
};

const TypingAnimation = () => (
    <div className="flex items-center space-x-1.5 p-2">
        {[0, 1, 2].map(i => <div key={i} className="w-1.5 h-1.5 bg-gray-400/70 rounded-full animate-pulse" style={{ animationDuration: "1s", animationDelay: `${i * 300}ms` }}></div>)}
    </div>
);

const MessageArea = ({ messages, messagesEndRef }: { messages: Message[], messagesEndRef: React.RefObject<HTMLDivElement | null> }) => {
    const { user } = useAuth();
    return (
        <div className="flex-grow w-full max-w-4xl overflow-y-auto px-4 pt-20 pb-10">
            {messages.map((message) => (
                <div key={message.id} className={`flex flex-col items-start ${message.isUser ? 'items-end' : ''} mb-6`}>
                    <div className={`text-sm font-bold mb-2 ${message.isUser ? "text-blue-400" : "text-gray-300"}`}>
                        {message.isUser ? user?.username : "Nivara"}
                    </div>
                    <div className={`py-3 px-5 max-w-xl break-words whitespace-pre-wrap rounded-2xl ${message.isUser ? 'bg-gradient-to-br from-blue-600 to-purple-600 text-white' : 'bg-[#1E1F20] text-gray-200'}`}>
                        {message.toolStatus && <div className="text-xs text-gray-400 italic pb-2 border-b border-gray-600 mb-2">{message.toolStatus}</div>}
                        {message.isLoading && !message.content && !message.toolStatus ? <TypingAnimation /> : message.content}
                    </div>
                </div>
            ))}
            <div ref={messagesEndRef} />
        </div>
    );
};

// --- Page Components ---
const ChatPage = () => {
    const { token, user } = useAuth();
    const [messages, setMessages] = useState<Message[]>([]);
    const [currentMessage, setCurrentMessage] = useState("");
    const [isStreaming, setIsStreaming] = useState(false);
    const messagesEndRef = useRef<HTMLDivElement | null>(null);

    useEffect(() => {
        if (user && messages.length === 0) {
            setMessages([
                { id: Date.now(), content: `Hello, ${user.username}! I'm Nivara, your personal finance guide. How can I help you today?`, isUser: false }
            ]);
        }
    }, [user, messages.length]);

    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [messages]);

    const handleSubmit = async (e: FormEvent) => {
        e.preventDefault();
        if (!currentMessage.trim() || isStreaming || !token) return;

        const userMessage: Message = { id: Date.now(), content: currentMessage, isUser: true };
        const aiResponsePlaceholder: Message = { id: Date.now() + 1, content: "", isUser: false, isLoading: true };
        setMessages(prev => [...prev, userMessage, aiResponsePlaceholder]);
        const userMessageContent = currentMessage;
        setCurrentMessage("");
        setIsStreaming(true);

        try {
            const response = await fetch(`${API_URL}/chat-stream`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
                body: JSON.stringify({ message: userMessageContent }),
            });

            if (!response.body) return;
            const reader = response.body.getReader();
            const decoder = new TextDecoder();

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                const chunk = decoder.decode(value, { stream: true });
                const lines = chunk.split('\n\n').filter(line => line.trim().startsWith('data:'));

                for (const line of lines) {
                    const jsonStr = line.substring(6);
                    try {
                        const data: StreamedEvent = JSON.parse(jsonStr);

                        // --- REFACTORED STREAMING LOGIC ---
                        if (data.type === 'content' && data.content) {
                            // Append only the new chunk to the existing message content
                            setMessages(prev => prev.map(msg => 
                                msg.id === aiResponsePlaceholder.id 
                                ? { ...msg, content: msg.content + data.content, isLoading: true, toolStatus: null } 
                                : msg
                            ));
                        } else if (data.type === 'tool_start' && data.content) {
                            setMessages(prev => prev.map(msg => 
                                msg.id === aiResponsePlaceholder.id 
                                ? { ...msg, isLoading: true, toolStatus: data.content } 
                                : msg
                            ));
                        } else if (data.type === 'end') {
                            // The 'end' event signals the stream is fully complete.
                            setIsStreaming(false);
                            setMessages(prev => prev.map(msg => 
                                msg.id === aiResponsePlaceholder.id 
                                ? { ...msg, isLoading: false, toolStatus: null } 
                                : msg
                            ));
                            return; // Exit the loop
                        }
                    } catch (e) { console.error("Error parsing JSON:", e, jsonStr); }
                }
            }
        } catch (error) {
            console.error("Fetch error:", error);
            setMessages(prev => prev.map(msg => 
                msg.id === aiResponsePlaceholder.id 
                ? { ...msg, content: "Sorry, I encountered an error. Please try again.", isLoading: false } 
                : msg
            ));
        } finally {
            // Ensure streaming is always turned off, even if the stream breaks unexpectedly
            setIsStreaming(false);
            setMessages(prev => prev.map(msg => 
                msg.id === aiResponsePlaceholder.id 
                ? { ...msg, isLoading: false } 
                : msg
            ));
        }
    };

    const handleFileUpload = async (file: File) => {
        if (!token) return;

        const userMessage: Message = { id: Date.now(), content: `Uploaded file: ${file.name}`, isUser: true };
        const aiResponsePlaceholder: Message = { id: Date.now() + 1, content: "Uploading and processing...", isUser: false, isLoading: true };
        setMessages(prev => [...prev, userMessage, aiResponsePlaceholder]);
        setIsStreaming(true);

        const formData = new FormData();
        formData.append("file", file);

        try {
            const response = await fetch(`${API_URL}/upload-bank-statement`, {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${token}` },
                body: formData,
            });

            const data = await response.json();

            if (response.ok) {
                setMessages(prev => prev.map(msg => 
                    msg.id === aiResponsePlaceholder.id 
                    ? { ...msg, content: data.message, isLoading: false } 
                    : msg
                ));
            } else {
                setMessages(prev => prev.map(msg => 
                    msg.id === aiResponsePlaceholder.id 
                    ? { ...msg, content: `Upload failed: ${data.detail || 'Unknown error'}`, isLoading: false } 
                    : msg
                ));
            }

        } catch (error) {
            console.error("Upload error:", error);
            setMessages(prev => prev.map(msg => 
                msg.id === aiResponsePlaceholder.id 
                ? { ...msg, content: "Sorry, I encountered an error uploading the file.", isLoading: false } 
                : msg
            ));
        } finally {
            setIsStreaming(false);
        }
    };
    
    const startNewChat = () => {
        if (user) {
            setMessages([
                { id: Date.now(), content: `Hello, ${user.username}! How can I help you today?`, isUser: false }
            ]);
        }
    };

    return (
        <div className="w-full h-full flex flex-col items-center bg-[#131314] text-white relative">
            <Header onNewChat={startNewChat} />
            <MessageArea messages={messages} messagesEndRef={messagesEndRef} />
            <div className="w-full flex-shrink-0 flex justify-center">
                <InputBar 
                    currentMessage={currentMessage} 
                    setCurrentMessage={setCurrentMessage} 
                    onSubmit={handleSubmit} 
                    isStreaming={isStreaming} 
                    onFileUpload={handleFileUpload}
                />
            </div>
        </div>
    );
};

const AuthPage = () => {
    const { setToken } = useAuth();
    const [username, setUsername] = useState('');
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [isLogin, setIsLogin] = useState(true);
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);

    const handleAuth = async (e: FormEvent) => {
        e.preventDefault();
        setError('');
        setLoading(true);
        const url = `${API_URL}/${isLogin ? 'login' : 'signup'}`;
        const headers = isLogin ? { 'Content-Type': 'application/x-www-form-urlencoded' } : { 'Content-Type': 'application/json' };
        const body = isLogin ? new URLSearchParams({ username: email, password }) : JSON.stringify({ username, email, password });

        try {
            const response = await fetch(url, { method: 'POST', headers, body });
            const data = await response.json();
            if (!response.ok) throw new Error(data.detail || 'Authentication failed');
            setToken(data.access_token);
        } catch (err: unknown) {
            if (err instanceof Error) {
                setError(err.message);
            } else {
                setError('An unknown error occurred.');
            }
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="w-full max-w-md mx-auto p-8 bg-[#1E1F20] rounded-2xl shadow-lg border border-gray-700 text-white">
            <h2 className="text-3xl font-bold text-center text-gray-200 mb-2">{isLogin ? 'Welcome Back' : 'Create Account'}</h2>
            <p className="text-center text-gray-400 mb-8">to Nivara, your personal finance guide</p>
            <form onSubmit={handleAuth}>
                {!isLogin && <input type="text" value={username} onChange={(e) => setUsername(e.target.value)} placeholder="Username" required className="w-full px-4 py-3 mb-4 bg-[#2f3031] border border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"/>}
                <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Email Address" required className="w-full px-4 py-3 mb-4 bg-[#2f3031] border border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"/>
                <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Password" required minLength={6} className="w-full px-4 py-3 mb-6 bg-[#2f3031] border border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"/>
                {error && <p className="text-red-400 text-sm mb-4 text-center">{error}</p>}
                <button type="submit" disabled={loading} className="w-full bg-gradient-to-r from-blue-500 to-purple-500 text-white py-3 rounded-lg font-semibold hover:from-blue-600 hover:to-purple-600 disabled:opacity-50">
                    {loading ? 'Processing...' : (isLogin ? 'Login' : 'Sign Up')}
                </button>
            </form>
            <p className="text-center text-sm text-gray-400 mt-6">
                {isLogin ? "Don't have an account?" : "Already have an account?"}
                <button onClick={() => { setIsLogin(!isLogin); setError(''); }} className="text-blue-400 hover:text-blue-300 font-semibold ml-1">
                    {isLogin ? 'Sign Up' : 'Login'}
                </button>
            </p>
        </div>
    );
};

// --- Main App Component ---
export default function Home() {
    return (
        <AuthProvider>
            <main className="flex justify-center items-center bg-[#131314] min-h-screen h-screen">
                <AppContent />
            </main>
        </AuthProvider>
    );
}

const AppContent = () => {
    const { token, isLoading } = useAuth();

    if (isLoading) {
        return <div className="text-white">Loading Session...</div>;
    }

    return (
        <div className="w-full h-full flex justify-center items-center">
            {token ? <ChatPage /> : <AuthPage />}
        </div>
    );
};