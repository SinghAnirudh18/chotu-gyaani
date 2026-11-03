import React, { createContext, useContext, useEffect, useState } from 'react';
import { api } from '../api/client';
import { BusinessMembership, Language, User } from '../types';

interface AuthContextType {
  user: User | null;
  memberships: BusinessMembership[];
  activeBusiness: BusinessMembership | null;
  activeRole: string | null;
  language: Language;
  isLoading: boolean;
  setLanguage: (lang: Language) => void;
  login: (email: string, password: string) => Promise<void>;
  register: (data: { email: string; password: string; name: string; businessName?: string; preferred_language?: string }) => Promise<void>;
  createNewBusiness: (name: string) => Promise<void>;
  logout: () => Promise<void>;
  switchBusiness: (businessId: string) => void;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [memberships, setMemberships] = useState<BusinessMembership[]>([]);
  const [activeBusiness, setActiveBusiness] = useState<BusinessMembership | null>(null);
  const [language, setLanguageState] = useState<Language>(() => {
    return (localStorage.getItem('chotu_language') as Language) || 'hi-Latn';
  });
  const [isLoading, setIsLoading] = useState<boolean>(true);

  const setLanguage = (lang: Language) => {
    setLanguageState(lang);
    localStorage.setItem('chotu_language', lang);
  };

  const initAuth = async () => {
    const token = api.getToken();
    if (!token) {
      setIsLoading(false);
      return;
    }

    try {
      const res = await api.me();
      const userData = res.data.user;
      const mems = res.data.memberships || [];
      setUser(userData);
      setMemberships(mems);

      const savedBizId = api.getBusinessId();
      const matched = mems.find((m: BusinessMembership) => m.business_id === savedBizId);
      if (matched) {
        setActiveBusiness(matched);
      } else if (mems.length > 0) {
        setActiveBusiness(mems[0]);
        api.setBusinessId(mems[0].business_id);
      }
    } catch {
      api.clearSession();
      setUser(null);
      setMemberships([]);
      setActiveBusiness(null);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    initAuth();
  }, []);

  const login = async (email: string, password: string) => {
    setIsLoading(true);
    try {
      await api.login(email, password);
      const res = await api.me();
      const userData = res.data.user;
      const mems = res.data.memberships || [];
      setUser(userData);
      setMemberships(mems);

      if (mems.length > 0) {
        setActiveBusiness(mems[0]);
        api.setBusinessId(mems[0].business_id);
      }
    } finally {
      setIsLoading(false);
    }
  };

  const register = async (data: { email: string; password: string; name: string; businessName?: string; preferred_language?: string }) => {
    setIsLoading(true);
    try {
      await api.register({
        email: data.email,
        password: data.password,
        name: data.name,
        preferred_language: data.preferred_language,
      });

      // Automatically create business for new user
      const bizName = data.businessName?.trim() || `${data.name}'s Vyapaar`;
      await api.createBusiness({
        name: bizName,
        default_language: data.preferred_language || 'hi-Latn',
      });

      const res = await api.me();
      const userData = res.data.user;
      const mems = res.data.memberships || [];
      setUser(userData);
      setMemberships(mems);

      if (mems.length > 0) {
        setActiveBusiness(mems[0]);
        api.setBusinessId(mems[0].business_id);
      }
    } finally {
      setIsLoading(false);
    }
  };

  const createNewBusiness = async (name: string) => {
    setIsLoading(true);
    try {
      await api.createBusiness({
        name,
        default_language: language,
      });
      await initAuth();
    } finally {
      setIsLoading(false);
    }
  };

  const logout = async () => {
    await api.logout();
    setUser(null);
    setMemberships([]);
    setActiveBusiness(null);
  };

  const switchBusiness = (businessId: string) => {
    const found = memberships.find((m) => m.business_id === businessId);
    if (found) {
      setActiveBusiness(found);
      api.setBusinessId(businessId);
      window.location.reload();
    }
  };

  const refreshUser = async () => {
    await initAuth();
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        memberships,
        activeBusiness,
        activeRole: activeBusiness ? activeBusiness.role : null,
        language,
        isLoading,
        setLanguage,
        login,
        register,
        createNewBusiness,
        logout,
        switchBusiness,
        refreshUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

