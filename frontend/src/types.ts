export interface MaterialType {
  id: number;
  name: string;
  unit_price: number;
}

export interface OrderType {
  id: number;
  title: string;
  description: string;
  price: number | null;
  status: string;
  customer_id: number;
  created_at: string;
  updated_at: string;
  materials?: MaterialType[];
}

export interface UserType {
  id: number;
  email: string;
  first_name?: string;
  last_name?: string;
  is_active: boolean;
  created_at: string;
}

export interface LoginCredentials {
  email: string;
  password: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
}