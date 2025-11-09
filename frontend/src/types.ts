// ==================== MATERIAL TYPES ====================

export interface MaterialType {
  id: number;
  name: string;
  description?: string;
  unit_price: number;
  stock: number;
  unit: string;
  stock_value?: number;
}

export interface MaterialCreateInput {
  name: string;
  description?: string;
  unit_price: number;
  stock: number;
  unit: string;
}

export interface MaterialUpdateInput {
  name?: string;
  description?: string;
  unit_price?: number;
  stock?: number;
  unit?: string;
}

// ==================== CUSTOMER TYPES ====================

export type CustomerCategory = 'private' | 'business';

export interface Customer {
  id: number;
  first_name: string;
  last_name: string;
  company_name?: string | null;
  email: string;
  phone?: string | null;
  mobile?: string | null;
  street?: string | null;
  city?: string | null;
  postal_code?: string | null;
  country: string;
  customer_type: CustomerCategory;
  source?: string | null;
  notes?: string | null;
  tags: string[];
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface CustomerListItem {
  id: number;
  first_name: string;
  last_name: string;
  company_name?: string | null;
  email: string;
  phone?: string | null;
  customer_type: CustomerCategory;
  tags: string[];
  is_active: boolean;
}

export interface CustomerCreateInput {
  first_name: string;
  last_name: string;
  company_name?: string;
  email: string;
  phone?: string;
  mobile?: string;
  street?: string;
  city?: string;
  postal_code?: string;
  country?: string;
  customer_type?: CustomerCategory;
  source?: string;
  notes?: string;
  tags?: string[];
}

export interface CustomerUpdateInput {
  first_name?: string;
  last_name?: string;
  company_name?: string | null;
  email?: string;
  phone?: string | null;
  mobile?: string | null;
  street?: string | null;
  city?: string | null;
  postal_code?: string | null;
  country?: string;
  customer_type?: CustomerCategory;
  source?: string | null;
  notes?: string | null;
  tags?: string[];
  is_active?: boolean;
}

export interface CustomerStats {
  customer_id: number;
  order_count: number;
  total_spent: number;
  last_order_date?: string | null;
}

// ==================== ORDER TYPES ====================

export type OrderStatus = 'new' | 'in_progress' | 'completed' | 'delivered';

export interface OrderType {
  id: number;
  title: string;
  description: string;
  price: number | null;
  status: OrderStatus;
  customer_id: number;
  deadline?: string | null;
  created_at: string;
  updated_at: string;
  materials?: MaterialType[];
}

export interface OrderCreateInput {
  title: string;
  description: string;
  price?: number;
  customer_id: number;
  deadline?: string;
  status?: OrderStatus;
}

export interface OrderUpdateInput {
  title?: string;
  description?: string;
  price?: number;
  deadline?: string | null;
  status?: OrderStatus;
}

// ==================== USER TYPES ====================

export interface UserType {
  id: number;
  email: string;
  first_name?: string;
  last_name?: string;
  is_active: boolean;
  created_at: string;
}

export interface UserCreateInput {
  email: string;
  password: string;
  first_name?: string;
  last_name?: string;
}

export interface UserUpdateInput {
  email?: string;
  password?: string;
  first_name?: string;
  last_name?: string;
  is_active?: boolean;
}

// ==================== AUTH TYPES ====================

export interface LoginCredentials {
  email: string;
  password: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
}

export interface AuthContextType {
  user: UserType | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (credentials: LoginCredentials) => Promise<void>;
  register: (userData: UserCreateInput) => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
}